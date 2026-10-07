"""TUMO Astana learner schedule lookup API."""

from __future__ import annotations

import hmac
import logging
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import Settings
from .models import HealthResponse, LearnerOut, LearnerRecord, LookupRequest, LookupResponse
from .sheet import name_tokens
from .sources import build_source
from .store import LearnerStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

MIN_TOKENS = 2  # name + surname, so a single word can't list everyone named "Али"
MIN_TOKEN_LEN = 2
MAX_RESULTS = 3  # more matches than this means the query is too vague to show anything


class RateLimiter:
    """Tiny in-memory sliding-window limiter to slow down name enumeration."""

    def __init__(self, per_minute: int):
        self.per_minute = per_minute
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> None:
        if self.per_minute <= 0:
            return
        now = time.monotonic()
        hits = self._hits[key]
        while hits and now - hits[0] > 60:
            hits.popleft()
        if len(hits) >= self.per_minute:
            raise HTTPException(429, "Too many lookups. Please wait a minute and try again.")
        hits.append(now)
        if len(self._hits) > 10_000:  # bound memory
            self._hits = defaultdict(deque, {k: v for k, v in self._hits.items() if v})


def to_public(r: LearnerRecord) -> LearnerOut:
    """Map an internal record to the public shape — only fields the card shows."""
    return LearnerOut(
        full_name=r.full_name,
        schedule=r.schedule or None,
        schedule_kk=r.schedule_kk or None,
        self_study_day=r.self_study_day or None,
        self_study_day_kk=r.self_study_day_kk or None,
        coach=r.coach or None,
        coach_email=r.coach_email or None,
        stage=r.stage or None,
        stage_code=r.stage_code or None,
        status=r.status or None,
        status_code=r.status_code or None,
        note=r.note or None,
        note_kk=r.note_kk or None,
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    store = LearnerStore(build_source(settings), settings.cache_file, settings.sync_interval_seconds)
    limiter = RateLimiter(settings.lookup_rate_limit_per_minute)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await store.start()
        yield
        await store.stop()

    app = FastAPI(title="TUMO Astana Learner Schedule", version="2.0.0", lifespan=lifespan)
    app.state.store = store
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    def rate_limit(request: Request) -> None:
        limiter.check(request.client.host if request.client else "unknown")

    @app.post("/api/schedule/lookup", response_model=LookupResponse, dependencies=[Depends(rate_limit)])
    def lookup(req: LookupRequest) -> LookupResponse:
        snap = store.snapshot
        if snap is None:
            raise HTTPException(503, "Schedule data is temporarily unavailable. Please try again shortly.")
        updated = snap.fetched_at

        tokens = [t for t in name_tokens(req.query) if len(t) >= MIN_TOKEN_LEN]
        if len(tokens) < MIN_TOKENS:
            return LookupResponse(status="need_full_name", data_updated_at=updated)

        found = store.search(tokens)
        if not found:
            return LookupResponse(status="not_found", data_updated_at=updated)
        active = [r for r in found if r.active]
        if not active:
            return LookupResponse(status="inactive", data_updated_at=updated)
        if len(active) > MAX_RESULTS:
            return LookupResponse(status="too_many", data_updated_at=updated)
        return LookupResponse(status="ok", results=[to_public(r) for r in active], data_updated_at=updated)

    @app.get("/api/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        snap = store.snapshot
        if snap is None:
            status = "no_data"
        elif store.last_sync_error:
            status = "degraded"  # serving cached data while the source is failing
        else:
            status = "ok"
        return HealthResponse(
            status=status,
            source=store.source.name,
            learners_cached=len(snap.learners) if snap else 0,
            data_updated_at=snap.fetched_at if snap else None,
            last_sync_error=store.last_sync_error,
        )

    @app.post("/api/admin/refresh", response_model=HealthResponse)
    async def admin_refresh(x_admin_token: str = Header(default="")) -> HealthResponse:
        if not settings.admin_token or not hmac.compare_digest(x_admin_token, settings.admin_token):
            raise HTTPException(404)
        await store.refresh_async()
        return health()

    # Optionally serve the built Vue app (frontend/dist) so everything deploys as one process.
    static_dir = settings.static_dir
    if static_dir and (static_dir / "index.html").is_file():
        app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str) -> FileResponse:
            if path.startswith("api/"):
                raise HTTPException(404)
            file = (static_dir / path).resolve()
            if path and file.is_file() and file.is_relative_to(static_dir.resolve()):
                return FileResponse(file)
            return FileResponse(static_dir / "index.html")

    return app


app = create_app()
