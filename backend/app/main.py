"""TUMO Astana student lookup API."""

from __future__ import annotations

import hmac
import logging
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from .config import Settings
from .models import (
    HealthResponse,
    LinksOut,
    LookupRequest,
    LookupResponse,
    SelfStudyOut,
    Snapshot,
    StudentDashboardOut,
    StudentRecord,
    WorkshopOut,
)
from .sources import build_source
from .store import StudentStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


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


def to_dashboard(student: StudentRecord, snap: Snapshot) -> StudentDashboardOut:
    """Map an internal record to the public shape — only fields the dashboard needs."""
    workshops = [snap.workshops[w] for w in student.workshop_ids if w in snap.workshops]
    whatsapp = (
        student.whatsapp_link
        or next((w.whatsapp_link for w in workshops if w.whatsapp_link), "")
        or snap.links.get("whatsapp_default", "")
    )
    self_study = (
        SelfStudyOut(days=student.self_study_days, time=student.self_study_time)
        if student.self_study_days or student.self_study_time
        else None
    )
    return StudentDashboardOut(
        first_name=student.first_name,
        last_name=student.last_name,
        self_study=self_study,
        workshops=[
            WorkshopOut(name=w.name, teacher=w.teacher or None, room=w.room or None, days=w.days, time=w.time)
            for w in workshops
        ],
        links=LinksOut(whatsapp=whatsapp or None),
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    store = StudentStore(build_source(settings), settings.cache_file, settings.sync_interval_seconds)
    limiter = RateLimiter(settings.lookup_rate_limit_per_minute)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await store.start()
        yield
        await store.stop()

    app = FastAPI(title="TUMO Astana Student Lookup", version="1.0.0", lifespan=lifespan)
    app.state.store = store
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    def rate_limit(request: Request) -> None:
        limiter.check(request.client.host if request.client else "unknown")

    def lookup(req: LookupRequest) -> LookupResponse:
        snap = store.snapshot
        if snap is None:
            raise HTTPException(503, "Student data is temporarily unavailable. Please try again shortly.")
        matches = store.find(req.query())
        if not matches:
            return LookupResponse(
                status="not_found",
                message="We couldn't find that name. Check the spelling or ask a TUMO coach for help.",
                data_updated_at=snap.fetched_at,
            )
        active = [s for s in matches if s.active]
        if not active:
            return LookupResponse(
                status="inactive",
                message="Your enrollment isn't active right now. Please talk to the TUMO front desk.",
                data_updated_at=snap.fetched_at,
            )
        return LookupResponse(
            status="ok",
            message="Found",
            students=[to_dashboard(s, snap) for s in active],
            data_updated_at=snap.fetched_at,
        )

    @app.post("/api/students/lookup", response_model=LookupResponse, dependencies=[Depends(rate_limit)])
    def lookup_post(req: LookupRequest) -> LookupResponse:
        return lookup(req)

    @app.get("/api/students/lookup", response_model=LookupResponse, dependencies=[Depends(rate_limit)])
    def lookup_get(
        first_name: str = Query("", max_length=60),
        last_name: str = Query("", max_length=60),
        full_name: str = Query("", max_length=120),
    ) -> LookupResponse:
        """Convenience GET variant. Prefer POST: names in query strings end up in access logs."""
        try:
            req = LookupRequest(first_name=first_name, last_name=last_name, full_name=full_name)
        except ValidationError as exc:
            raise HTTPException(422, exc.errors()[0]["msg"]) from None
        return lookup(req)

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
            students_cached=len(snap.students) if snap else 0,
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
            return FileResponse(static_dir / "index.html")  # SPA fallback for client-side routes

    return app


app = create_app()
