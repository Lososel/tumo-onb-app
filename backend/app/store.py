"""Resilient cache in front of the data source.

- Lookups are served from an in-memory snapshot (a dict lookup — no network on the request path).
- A background task re-syncs from the source every SYNC_INTERVAL_SECONDS.
- If a sync fails (quota, network, bad credentials), the last good snapshot keeps serving.
- The last good snapshot is persisted to disk, so a restart during an outage is still instant.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

from .models import LearnerRecord, Snapshot
from .services.sheets import SheetsConfigError, matches, parse_tabs
from .sources import DataSource

log = logging.getLogger(__name__)


class LearnerStore:
    def __init__(
        self,
        source: DataSource,
        cache_file: Path,
        sync_interval: int,
        tab_filter: str = "",
        fallback_source: DataSource | None = None,
    ):
        self.source = source
        self.fallback_source = fallback_source  # opt-in mock data when live + cache are both missing
        self.tab_filter = tab_filter
        self.cache_file = cache_file
        self.sync_interval = sync_interval
        self._snapshot: Snapshot | None = None
        self._lock = threading.Lock()
        self.last_sync_error: str | None = None
        self.last_sync_attempt: datetime | None = None
        self.serving_fallback = False
        self._task: asyncio.Task | None = None

    @property
    def origin(self) -> str:
        """What a snapshot must have been built from to be served (file id/path + tab filter)."""
        return f"{getattr(self.source, 'origin', self.source.name)}|{self.tab_filter}"

    # ---------- reads ----------

    @property
    def snapshot(self) -> Snapshot | None:
        return self._snapshot

    def search(self, query_tokens: list[str]) -> list[LearnerRecord]:
        """Linear scan — a few thousand learners take well under a millisecond."""
        snap = self._snapshot
        if snap is None or not query_tokens:
            return []
        return [r for r in snap.learners if matches(query_tokens, r.tokens)]

    # ---------- writes ----------

    def _install(self, snapshot: Snapshot) -> None:
        with self._lock:  # single reference swap; readers always see a complete snapshot
            self._snapshot = snapshot

    def load_from_disk(self) -> bool:
        """Load the last good snapshot — only if it came from the currently configured source.

        A cache from another sheet (e.g. after GOOGLE_SHEET_ID or TAB_FILTER changed) is
        discarded so stale data from the old sheet is never served.
        """
        try:
            snapshot = Snapshot.model_validate(json.loads(self.cache_file.read_text(encoding="utf-8")))
            if snapshot.origin != self.origin:
                log.warning("Discarding cache built from a different source/tab filter")
                self.cache_file.unlink(missing_ok=True)
                return False
            self._install(snapshot)
            log.info("Loaded cached snapshot from %s", self.cache_file)
            return True
        except FileNotFoundError:
            return False
        except Exception:
            log.exception("Ignoring unreadable cache file %s", self.cache_file)
            return False

    def _persist(self, snapshot: Snapshot) -> None:
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.cache_file.with_suffix(".tmp")
            # The snapshot can hold temporary passwords: owner-only permissions from the first byte.
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(snapshot.model_dump_json())
            os.chmod(tmp, 0o600)  # in case a stale .tmp existed with wider permissions
            os.replace(tmp, self.cache_file)  # atomic: never leaves a half-written cache
        except Exception:
            log.exception("Could not persist snapshot to %s", self.cache_file)

    def refresh(self) -> bool:
        """Fetch from the source. Never raises: on any failure (bad credentials, auth/network
        errors, a broken sheet) the previous snapshot keeps serving; with no snapshot at all,
        the opt-in fallback dataset is loaded."""
        self.last_sync_attempt = datetime.now(timezone.utc)
        try:
            snapshot = parse_tabs(self.source.fetch(), source=self.source.name, tab_filter=self.tab_filter)
            snapshot.origin = self.origin
        except Exception as exc:
            # Config errors carry a safe, actionable message; for anything else keep only the
            # type, since messages can contain URLs/IDs we don't want on a public endpoint.
            self.last_sync_error = (
                f"{type(exc).__name__}: {exc}" if isinstance(exc, SheetsConfigError) else type(exc).__name__
            )
            log.warning("Sync from %s failed (%s: %s); serving cached data", self.source.name,
                        type(exc).__name__, exc)
            if self._snapshot is None:
                self._load_fallback()
            return False
        self._install(snapshot)
        self._persist(snapshot)
        self.serving_fallback = False
        self.last_sync_error = None
        log.info("Synced %d learners from %s", len(snapshot.learners), self.source.name)
        return True

    def _load_fallback(self) -> None:
        if self.fallback_source is None:
            log.warning("No cached snapshot and no fallback: lookups answer 'unavailable' until a sync works")
            return
        try:
            raw = self.fallback_source.fetch()
            snapshot = parse_tabs(raw, source=f"{self.fallback_source.name}-fallback")
        except Exception:
            log.exception("Fallback dataset could not be loaded either")
            return
        self._install(snapshot)  # deliberately not persisted: the cache only ever holds live data
        self.serving_fallback = True
        log.warning(
            "Serving FALLBACK dataset (%d learners) until a live sync succeeds", len(snapshot.learners)
        )

    async def refresh_async(self) -> bool:
        return await asyncio.to_thread(self.refresh)

    # ---------- background sync ----------

    async def _loop(self, skip_first: bool) -> None:
        if skip_first:
            await asyncio.sleep(self.sync_interval)
        while True:
            try:
                await self.refresh_async()
            except Exception:  # refresh() already catches everything; belt and braces
                log.exception("Unexpected error in background sync; retrying next interval")
            await asyncio.sleep(self.sync_interval)

    async def start(self, initial_timeout: float = 10.0) -> None:
        """Sync immediately on startup so sheet edits are visible right after a (re)deploy.

        A matching disk cache is served while that first sync runs in the background; with no
        usable cache, startup waits (bounded) for it. Never raises, so a Google outage or
        misconfiguration can't stop the app from starting.
        """
        synced = False
        try:
            if self.load_from_disk():
                pass  # serve the cache now; the loop below syncs immediately (skip_first=False)
            else:
                synced = await asyncio.wait_for(self.refresh_async(), timeout=initial_timeout)
        except asyncio.TimeoutError:
            log.warning("Initial sync timed out; continuing in the background")
            if self._snapshot is None:
                self._load_fallback()
        except Exception:
            log.exception("Initial sync failed unexpectedly; continuing in the background")
        if self._task is None:
            self._task = asyncio.create_task(self._loop(skip_first=synced))

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
