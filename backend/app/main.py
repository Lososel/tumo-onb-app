"""TUMO Astana learner schedule lookup API — app factory."""

from __future__ import annotations

import hmac
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api.endpoints import schedule
from .core.config import Settings
from .core.rate_limit import RateLimiter
from .schemas.schedule import HealthResponse
from .sources import build_source
from .store import LearnerStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    store = LearnerStore(build_source(settings), settings.cache_file, settings.sync_interval_seconds)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await store.start()
        yield
        await store.stop()

    app = FastAPI(title="TUMO Astana Learner Schedule", version="3.0.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.store = store
    app.state.limiter = RateLimiter(settings.lookup_rate_limit_per_minute)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    app.include_router(schedule.router)

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
