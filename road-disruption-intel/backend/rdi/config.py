"""Application configuration.

Configuration is read from environment variables, optionally loaded from a
gitignored ``.env`` file in the project root. Secrets (API keys) are never
read by the frontend; see ``rdi.secrets`` for how keys entered in the UI are
stored.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:  # python-dotenv is optional at import time (tests may run without it)
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent

if load_dotenv is not None:
    load_dotenv(PROJECT_DIR / ".env", override=False)


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    try:
        return int(raw) if raw not in (None, "") else default
    except ValueError:
        return default


def _detect_data_dir() -> Path:
    """Historical data lives in ``<project>/data`` or a sibling ``../data``."""
    explicit = os.getenv("HISTORICAL_DATA_DIR")
    if explicit:
        return Path(explicit).expanduser().resolve()
    for candidate in (PROJECT_DIR / "data", PROJECT_DIR.parent / "data"):
        if candidate.is_dir():
            return candidate.resolve()
    return (PROJECT_DIR / "data").resolve()


@dataclass
class Settings:
    runtime_dir: Path = field(default_factory=lambda: Path(os.getenv("RUNTIME_DIR", str(PROJECT_DIR / "runtime"))).resolve())
    historical_data_dir: Path = field(default_factory=_detect_data_dir)
    database_url: str = ""
    host: str = field(default_factory=lambda: os.getenv("APP_HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: _int("APP_PORT", 8000))
    access_token: str = field(default_factory=lambda: os.getenv("APP_ACCESS_TOKEN", ""))
    allow_remote: bool = field(default_factory=lambda: _bool("APP_ALLOW_REMOTE", False))
    cors_origins: list[str] = field(default_factory=lambda: [o.strip() for o in os.getenv(
        "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()])
    scheduler_enabled: bool = field(default_factory=lambda: _bool("SCHEDULER_ENABLED", True))
    job_workers: int = field(default_factory=lambda: max(1, min(4, _int("JOB_WORKERS", 2))))
    nominatim_url: str = field(default_factory=lambda: os.getenv("NOMINATIM_URL", "https://nominatim.openstreetmap.org"))
    nominatim_contact: str = field(default_factory=lambda: os.getenv("NOMINATIM_CONTACT_EMAIL", ""))
    geocoding_online: bool = field(default_factory=lambda: _bool("GEOCODING_ONLINE", True))
    max_upload_mb: int = field(default_factory=lambda: _int("MAX_UPLOAD_MB", 200))
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    frontend_dist: Path = field(default_factory=lambda: PROJECT_DIR / "frontend" / "dist")

    def __post_init__(self) -> None:
        if not self.database_url:
            self.database_url = os.getenv("DATABASE_URL") or f"sqlite:///{(self.runtime_dir / 'rdi.db').as_posix()}"

    # Derived paths -------------------------------------------------------
    @property
    def backups_dir(self) -> Path:
        return self.runtime_dir / "backups"

    @property
    def logs_dir(self) -> Path:
        return self.runtime_dir / "logs"

    @property
    def uploads_dir(self) -> Path:
        return self.runtime_dir / "uploads"

    @property
    def reports_dir(self) -> Path:
        return self.runtime_dir / "reports"

    @property
    def secrets_file(self) -> Path:
        return self.runtime_dir / "secrets.json"

    @property
    def sqlite_path(self) -> Path | None:
        if self.database_url.startswith("sqlite:///"):
            return Path(self.database_url[len("sqlite:///"):])
        return None

    def ensure_dirs(self) -> None:
        for d in (self.runtime_dir, self.backups_dir, self.logs_dir, self.uploads_dir, self.reports_dir):
            d.mkdir(parents=True, exist_ok=True)


settings = Settings()


def reload_settings(**overrides) -> Settings:
    """Rebuild the global settings object (used by tests)."""
    global settings
    new = Settings(**overrides)
    settings.__dict__.update(new.__dict__)
    return settings
