"""API: startup, health, pagination/filtering, exports, dashboard, secrets and access control."""
import json
import logging
import os
import sqlite3
from pathlib import Path

from sqlalchemy import func, select

from rdi.config import PROJECT_DIR, settings
from rdi.db.models import Article, SchemaVersion
from rdi.db.session import SessionLocal, init_db
from rdi.logging_setup import RedactingFilter, redact


def test_health_and_ready(client):
    assert client.get("/api/health").json()["status"] == "ok"
    r = client.get("/api/ready").json()
    assert r["ready"] is True and r["checks"]["database"]["ok"]


def test_init_db_idempotent_and_backup_before_migration():
    info = init_db()
    assert info["new_database"] is False
    with SessionLocal() as db:  # simulate an older schema version
        db.query(SchemaVersion).delete()
        db.add(SchemaVersion(version=0, note="old"))
        db.commit()
    info = init_db()
    assert info["backup"] and Path(info["backup"]).exists()
    con = sqlite3.connect(info["backup"])
    assert con.execute("select count(*) from articles").fetchone()[0] >= 0
    con.close()


def test_records_pagination_filters_and_sort(client):
    with SessionLocal() as db:
        total = db.scalar(select(func.count(Article.id)).where(Article.near_duplicate_of.is_(None)))
    r = client.get("/api/records?page=1&page_size=2").json()
    assert r["total"] == total and len(r["items"]) == 2 and r["pages"] == (total + 1) // 2
    r2 = client.get("/api/records?page=2&page_size=2").json()
    assert {x["id"] for x in r["items"]}.isdisjoint({x["id"] for x in r2["items"]})
    q = client.get("/api/records?q=NH%2048").json()
    assert q["total"] >= 1 and all("48" in (x["title"] + str(x["highway_number"])) for x in q["items"])
    unc = client.get("/api/records?classification_status=UNCLASSIFIED&page_size=200").json()
    assert all(x["classification_status"] == "UNCLASSIFIED" for x in unc["items"])
    s = client.get("/api/records?sort=title&order=asc&page_size=50").json()["items"]
    assert [x["title"] for x in s] == sorted(x["title"] for x in s)
    assert client.get("/api/records?page_size=1000").status_code == 422
    assert client.get("/api/records?date_from=notadate").status_code == 422
    empty = client.get("/api/records?q=zzzz-no-such-term").json()
    assert empty["total"] == 0 and empty["items"] == []


def test_record_detail_and_404(client):
    rid = client.get("/api/records?page_size=1").json()["items"][0]["id"]
    d = client.get(f"/api/records/{rid}").json()
    assert d["article"]["id"] == rid and d["sightings"]
    assert client.get("/api/records/does-not-exist").status_code == 404


def test_review_requires_classification(client):
    rid = client.get("/api/records?classification_status=UNCLASSIFIED&page_size=1").json()["items"][0]["id"]
    r = client.post(f"/api/records/{rid}/review", json={"decision": "APPROVED"})
    assert r.status_code == 409


def test_csv_and_json_export(client):
    r = client.get("/api/records/export?format=csv&q=Vasai")
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    lines = r.text.lstrip("﻿").splitlines()
    assert lines[0].startswith("# Road Disruption Intelligence export") and lines[1].startswith("id,title")
    assert len(lines) >= 3
    j = client.get("/api/records/export?format=json&q=Vasai")
    data = json.loads(j.text)
    assert data["generated_at"] and data["filters"] == {"q": "Vasai"} and len(data["records"]) == len(lines) - 2
    assert client.get("/api/records/export?format=xml").status_code == 422
    inc = client.get("/api/incidents/export?format=json").json()
    assert "incidents" in inc


def test_dashboard_metrics_match_database(client):
    d = client.get("/api/dashboard/summary").json()
    with SessionLocal() as db:
        unique = db.scalar(select(func.count(Article.id)).where(Article.near_duplicate_of.is_(None)))
        classified = db.scalar(select(func.count(Article.id)).where(Article.current_classification_id.is_not(None)))
    assert d["metrics"]["unique_articles"] == unique
    assert d["metrics"]["classified"] == classified
    assert set(d["definitions"]) >= {"active_incidents", "unique_articles"}
    assert client.get("/api/dashboard/summary?category=CLOSURE&date_from=2026-01-01").status_code == 200
    assert client.get("/api/quality").status_code == 200
    assert client.get("/api/reports/summary?date_from=2026-01-01&date_to=2026-12-31").status_code == 200


def test_incident_api_and_map(client):
    r = client.get("/api/incidents").json()
    assert r["total"] >= 1
    iid = r["items"][0]["id"]
    d = client.get(f"/api/incidents/{iid}").json()
    assert d["incident"]["id"] == iid and "allowed_transitions" in d
    assert client.post(f"/api/incidents/{iid}/status", json={"status": "BOGUS"}).status_code == 409
    m = client.get("/api/map/incidents").json()
    assert m["type"] == "FeatureCollection" and m["meta"]["mapped"] + m["meta"]["unmapped"] == m["meta"]["total_matching"]
    for f in m["features"]:
        lon, lat = f["geometry"]["coordinates"]
        assert 6 <= lat <= 37.6 and 68 <= lon <= 97.5
        assert f["properties"]["geo_precision"] in ("CITY", "LOCALITY", "MANUAL")
    assert client.post(f"/api/incidents/{iid}/merge", json={"target_id": iid}).status_code == 400  # needs confirm


def test_secrets_never_returned(client):
    secret = "sk-unit-test-secret-ABCDEFGH123"
    r = client.put("/api/secrets/OPENAI_API_KEY", json={"value": secret})
    assert r.status_code == 200 and r.json()["configured"] is True
    for path in ("/api/secrets", "/api/llm/config", "/api/system/info", "/api/settings/public", "/api/audit?page_size=200"):
        assert secret not in client.get(path).text, path
    assert client.put("/api/secrets/UNKNOWN_KEY", json={"value": "x"}).status_code == 422
    assert client.delete("/api/secrets/OPENAI_API_KEY").json()["removed"] is True
    assert client.get("/api/secrets").json()["secrets"][0]["configured"] in (False, True)
    assert secret not in (settings.secrets_file.read_text() if settings.secrets_file.exists() else "")


def test_log_redaction():
    assert "[REDACTED]" in redact("Authorization: Bearer abc.def.ghi")
    assert "sk-abcdefgh1234" not in redact("key sk-abcdefgh1234 leaked")
    assert "hunter2xyz" not in redact("api_key=hunter2xyz&q=1")
    rec = logging.LogRecord("x", logging.INFO, __file__, 1, "token=%s", ("supersecretvalue",), None)
    RedactingFilter().filter(rec)
    assert "supersecretvalue" not in rec.getMessage()


def test_gitignore_protects_secrets_and_runtime():
    gi = (PROJECT_DIR / ".gitignore").read_text()
    for entry in (".env", "runtime/", ".venv/"):
        assert entry in gi
    example = (PROJECT_DIR / ".env.example").read_text()
    assert "sk-" not in example and "APP_HOST=127.0.0.1" in example


def test_access_token_enforced(monkeypatch):
    from fastapi.testclient import TestClient
    from rdi.main import create_app
    monkeypatch.setattr(settings, "access_token", "a-very-long-test-token-123")
    with TestClient(create_app(start_background=False)) as c:
        assert c.get("/api/health").status_code == 200  # liveness stays open
        assert c.get("/api/records").status_code == 401
        assert c.get("/api/records", headers={"Authorization": "Bearer wrong"}).status_code == 401
        assert c.get("/api/records", headers={"Authorization": "Bearer a-very-long-test-token-123"}).status_code == 200


def test_server_refuses_unprotected_remote_bind(monkeypatch):
    from rdi import server
    monkeypatch.setattr(settings, "host", "0.0.0.0")
    monkeypatch.setattr(settings, "access_token", "")
    assert server.main() == 2


def test_source_update_validation(client):
    assert client.patch("/api/sources/google_news_india", json={"poll_interval_minutes": 5}).status_code == 422
    assert client.patch("/api/sources/official_feeds", json={"config": {"feeds": ["file:///etc/passwd"]}}).status_code == 422
    r = client.patch("/api/sources/official_feeds", json={"config": {"feeds": ["https://example.gov.in/rss.xml"]}})
    assert r.status_code == 200 and r.json()["configuration_status"] == "CONFIGURED"
    assert client.get("/api/sources").json()["sources"]


def test_security_headers_and_spa(client):
    r = client.get("/api/health")
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"
    assert client.get("/api/does-not-exist").status_code == 404
    assert client.get("/some/client/route").status_code in (200, 503)


def test_settings_validation(client):
    assert client.put("/api/settings/incidents", json={"stale_after_hours": "abc"}).status_code == 422
    assert client.put("/api/settings/incidents", json={"unknown": 1}).status_code == 422
    assert client.put("/api/settings/nope", json={}).status_code == 404
    pub = client.get("/api/settings/public").json()
    assert pub["branding"]["company_name"].startswith("Aviral Consulting")


def test_env_file_not_committed():
    assert not (PROJECT_DIR / ".env").exists() or ".env" in (PROJECT_DIR / ".gitignore").read_text()
    assert os.environ.get("APP_ACCESS_TOKEN", "") == ""


def test_timestamps_are_utc_marked(client):
    """Naive timestamps without 'Z' are misread by browsers as local time (bug found in manual testing)."""
    import re
    client.post("/api/system/backup")
    pattern = re.compile(r'"(\w*_at|created|time)": "(\d{4}-\d{2}-\d{2}T[^"]*)"')
    for path in ("/api/sources", "/api/system/info", "/api/records?page_size=5", "/api/incidents?page_size=5", "/api/jobs"):
        for key, value in pattern.findall(client.get(path).text):
            assert value.endswith("Z"), f"{path} {key}={value}"
