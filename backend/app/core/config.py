"""Runtime settings, read from environment variables (and an optional backend/.env file)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

_FALSE = {"0", "false", "no", "off", ""}


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
    csv_path: Path = field(default_factory=lambda: BACKEND_DIR / "data" / "csv")  # file or folder
    cache_file: Path = field(default_factory=lambda: BACKEND_DIR / "data" / "cache" / "snapshot.json")
    sync_interval_seconds: int = 300
    # Only tabs whose name contains this text are searched (case/space-insensitive), e.g.
    # "4 поток". Empty = all tabs. If no tab matches, all tabs are used (logged as a warning).
    tab_filter: str = ""
    cors_origins: tuple[str, ...] = ("http://localhost:5173",)
    lookup_rate_limit_per_minute: int = 30
    # Reverse proxies in front of the app that append to X-Forwarded-For (Render: 1). The client
    # IP for rate limiting is the Nth entry from the right; 0 = use the socket peer address.
    proxy_hops: int = 0
    admin_token: str = ""  # enables POST /api/admin/refresh when set
    static_dir: Path | None = None  # built frontend to serve (optional)
    # EXPOSE_TEMP_PASSWORD: include the sheet's temporary password in lookup responses.
    # Off unless explicitly enabled; turn it off again once onboarding is over.
    expose_temp_password: bool = False

    @classmethod
    def from_env(cls) -> "Settings":
        _load_dotenv(BACKEND_DIR / ".env")
        env = os.environ.get
        return cls(
            data_source=env("DATA_SOURCE", "mock").strip().lower(),
            google_credentials_file=_resolve(env("GOOGLE_CREDENTIALS_FILE", "credentials.json")),
            google_sheet_id=env("GOOGLE_SHEET_ID", "").strip(),
            mock_file=_resolve(env("MOCK_FILE", "data/mock_sheet.json")),
            csv_path=_resolve(env("CSV_PATH", "data/csv")),
            cache_file=_resolve(env("CACHE_FILE", "data/cache/snapshot.json")),
            sync_interval_seconds=max(30, int(env("SYNC_INTERVAL_SECONDS", "300"))),
            tab_filter=env("TAB_FILTER", "").strip(),
            cors_origins=tuple(
                o.strip() for o in env("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()
            ),
            lookup_rate_limit_per_minute=int(env("LOOKUP_RATE_LIMIT_PER_MINUTE", "30")),
            proxy_hops=max(0, int(env("PROXY_HOPS", "0"))),
            admin_token=env("ADMIN_TOKEN", "").strip(),
            static_dir=_resolve(env("STATIC_DIR", "../frontend/dist")),
            expose_temp_password=env("EXPOSE_TEMP_PASSWORD", "false").strip().lower() not in _FALSE,
        )
