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
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .models import Snapshot, StudentRecord
from .sheet import normalize_name, parse_tabs
from .sources import DataSource

log = logging.getLogger(__name__)


class StudentStore:
    def __init__(self, source: DataSource, cache_file: Path, sync_interval: int):
        self.source = source
        self.cache_file = cache_file
        self.sync_interval = sync_interval
        self._snapshot: Snapshot | None = None
        self._index: dict[str, list[StudentRecord]] = {}
        self._lock = threading.Lock()
        self.last_sync_error: str | None = None
        self.last_sync_attempt: datetime | None = None
        self._task: asyncio.Task | None = None

    # ---------- reads ----------

    @property
    def snapshot(self) -> Snapshot | None:
        return self._snapshot

    def find(self, name: str) -> list[StudentRecord]:
        key = normalize_name(name)
        return list(self._index.get(key, [])) if key else []

    # ---------- writes ----------

    def _install(self, snapshot: Snapshot) -> None:
        index: dict[str, list[StudentRecord]] = defaultdict(list)
        for s in snapshot.students:
            index[s.name_key].append(s)
        with self._lock:  # swap atomically; readers always see a complete snapshot
            self._snapshot = snapshot
            self._index = dict(index)

    def load_from_disk(self) -> bool:
        try:
            data = json.loads(self.cache_file.read_text(encoding="utf-8"))
            self._install(Snapshot.model_validate(data))
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
            tmp.write_text(snapshot.model_dump_json(), encoding="utf-8")
            os.replace(tmp, self.cache_file)  # atomic: never leaves a half-written cache
        except Exception:
            log.exception("Could not persist snapshot to %s", self.cache_file)

    def refresh(self) -> bool:
        """Fetch from the source; on any failure keep serving the previous snapshot."""
        self.last_sync_attempt = datetime.now(timezone.utc)
        try:
            snapshot = parse_tabs(self.source.fetch(), source=self.source.name)
        except Exception as exc:
            # Keep only the exception type: messages can contain URLs/IDs we don't want to expose.
            self.last_sync_error = type(exc).__name__
            log.warning("Sync from %s failed (%s); serving cached data", self.source.name, exc)
            return False
        self._install(snapshot)
        self._persist(snapshot)
        self.last_sync_error = None
        log.info("Synced %d students from %s", len(snapshot.students), self.source.name)
        return True

    async def refresh_async(self) -> bool:
        return await asyncio.to_thread(self.refresh)

    # ---------- background sync ----------

    async def _loop(self, skip_first: bool) -> None:
        if skip_first:
            await asyncio.sleep(self.sync_interval)
        while True:
            await self.refresh_async()
            await asyncio.sleep(self.sync_interval)

    async def start(self, initial_timeout: float = 10.0) -> None:
        """Serve the disk cache immediately if present; otherwise wait (bounded) for a first sync."""
        synced = False
        if not self.load_from_disk():
            try:
                synced = await asyncio.wait_for(self.refresh_async(), timeout=initial_timeout)
            except asyncio.TimeoutError:
                log.warning("Initial sync timed out; continuing in the background")
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
