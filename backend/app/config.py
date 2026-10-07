"""Runtime settings, read from environment variables (and an optional backend/.env file)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader so we don't need python-dotenv. Real env vars win."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _resolve(path: str) -> Path:
    p = Path(path)
    return p if p.is_absolute() else BACKEND_DIR / p


@dataclass(frozen=True)
class Settings:
    data_source: str = "mock"
    google_credentials_file: Path = field(default_factory=lambda: BACKEND_DIR / "credentials.json")
    google_sheet_id: str = ""
    mock_file: Path = field(default_factory=lambda: BACKEND_DIR / "data" / "mock_sheet.json")
    cache_file: Path = field(default_factory=lambda: BACKEND_DIR / "data" / "cache" / "snapshot.json")
    sync_interval_seconds: int = 300
    cors_origins: tuple[str, ...] = ("http://localhost:5173",)
    lookup_rate_limit_per_minute: int = 30
    admin_token: str = ""  # enables POST /api/admin/refresh when set
    static_dir: Path | None = None  # built frontend to serve (optional)

    @classmethod
    def from_env(cls) -> "Settings":
        _load_dotenv(BACKEND_DIR / ".env")
        env = os.environ.get
        return cls(
            data_source=env("DATA_SOURCE", "mock").strip().lower(),
            google_credentials_file=_resolve(env("GOOGLE_CREDENTIALS_FILE", "credentials.json")),
            google_sheet_id=env("GOOGLE_SHEET_ID", "").strip(),
            mock_file=_resolve(env("MOCK_FILE", "data/mock_sheet.json")),
            cache_file=_resolve(env("CACHE_FILE", "data/cache/snapshot.json")),
            sync_interval_seconds=max(30, int(env("SYNC_INTERVAL_SECONDS", "300"))),
            cors_origins=tuple(
                o.strip() for o in env("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()
            ),
            lookup_rate_limit_per_minute=int(env("LOOKUP_RATE_LIMIT_PER_MINUTE", "30")),
            admin_token=env("ADMIN_TOKEN", "").strip(),
            static_dir=_resolve(env("STATIC_DIR", "../frontend/dist")),
        )
