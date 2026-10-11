"""Test configuration.

Every test session uses a throw-away runtime directory and database. External
services (news APIs, LLMs, Nominatim) are replaced by ``httpx.MockTransport``;
no test needs network access, credentials or paid API credits.
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="rdi_test_"))
os.environ.update({
    "RUNTIME_DIR": str(_TMP / "runtime"),
    "HISTORICAL_DATA_DIR": str(_TMP / "data"),
    "SCHEDULER_ENABLED": "false",
    "GEOCODING_ONLINE": "false",
    "APP_ACCESS_TOKEN": "",
    "LOG_LEVEL": "WARNING",
})
for k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "NEWSAPI_KEY", "GNEWS_API_KEY", "REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET"):
    os.environ.pop(k, None)
(_TMP / "data").mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from rdi.db.session import SessionLocal, init_db  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session", autouse=True)
def _database():
    init_db()
    from rdi.services import job_handlers  # noqa: F401  register job types
    from rdi.services.acquisition import seed_sources
    with SessionLocal() as db:
        seed_sources(db)
    yield
    shutil.rmtree(_TMP, ignore_errors=True)


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


@pytest.fixture
def data_dir() -> Path:
    return _TMP / "data"


@pytest.fixture(scope="session")
def client(_database):
    from fastapi.testclient import TestClient
    from rdi.main import create_app
    with TestClient(create_app(start_background=False)) as c:
        yield c
