"""Historical import, duplicate suppression, malformed input and file safety."""
import shutil

import pytest
from sqlalchemy import func, select

from rdi.db.models import Article, ArticleSighting, ImportBatch
from rdi.services import importer, text
from conftest import FIXTURES


def _import(db, data_dir, name):
    target = data_dir / name
    shutil.copy(FIXTURES / name, target)
    batch = importer.create_batch(db, importer.resolve_safe(name))
    return importer.run_import(db, batch.id)


def test_url_canonicalisation():
    a = text.canonicalize_url("https://news.google.com/rss/articles/XYZ?oc=5")
    b = text.canonicalize_url("https://NEWS.google.com/articles/XYZ/?utm_source=t#frag")
    assert a == b == "https://news.google.com/articles/XYZ"
    assert text.canonicalize_url("javascript:alert(1)") is None
    assert text.canonicalize_url("https://www.x.com/a?b=2&a=1") == "https://x.com/a?a=1&b=2"


def test_timestamp_formats():
    assert text.parse_timestamp("Tue, 08 Sep 2026 06:50:00 GMT").isoformat() == "2026-09-08T06:50:00"
    assert text.parse_timestamp("20260910T214500Z").isoformat() == "2026-09-10T21:45:00"
    assert text.parse_timestamp("2026-09-03T08:00:00+05:30").isoformat() == "2026-09-03T02:30:00"
    assert text.parse_timestamp("not a date") is None


def test_historical_import_and_dedup(db, data_dir):
    b = _import(db, data_dir, "history_sample.jsonl")
    assert b.status == "COMPLETED"
    assert (b.discovered, b.imported, b.duplicate, b.invalid, b.failed) == (6, 3, 3, 0, 0)
    titles = [t for (t,) in db.execute(select(Article.title).where(Article.title.like("NH-48 closed near Vasai%")))]
    # Same headline from two different publishers is NOT merged (may be separate evidence)...
    assert len(titles) == 2
    # ...but the URL variants and same-source re-post are matched to the first article.
    methods = {m for (m,) in db.execute(select(ArticleSighting.match_method).where(ArticleSighting.origin == "data/history_sample.jsonl"))}
    assert {"new", "canonical_url", "title_fingerprint"} <= methods
    art = db.scalar(select(Article).where(Article.canonical_url == "https://news.google.com/articles/AAA111"))
    assert art.summary_text == "NH-48 closed near Vasai after truck overturns Times Now"  # HTML stripped
    assert art.query_city == "Mumbai" and art.prefilter_label == "LIKELY_RELEVANT"
    assert "<a href" in art.raw_snippet  # original snippet preserved for audit


def test_reimport_is_idempotent(db, data_dir):
    before = db.scalar(select(func.count(Article.id)))
    b = _import(db, data_dir, "history_sample.jsonl")
    assert b.imported == 0 and b.duplicate == 6
    assert db.scalar(select(func.count(Article.id))) == before


def test_original_file_untouched(data_dir):
    assert (data_dir / "history_sample.jsonl").read_bytes() == (FIXTURES / "history_sample.jsonl").read_bytes()


def test_malformed_rows_reported(db, data_dir):
    b = _import(db, data_dir, "malformed.jsonl")
    assert b.status == "COMPLETED_WITH_ERRORS"
    assert b.discovered == 7 and b.imported == 1 and b.invalid == 6 and b.failed == 0
    report = importer.error_report_csv(db, b.id)
    for reason in ("missing title", "malformed JSON", "not a JSON object", "invalid URL", "no URL", "implausible"):
        assert reason in report


def test_csv_and_json_array_import(db, data_dir):
    c = _import(db, data_dir, "sample.csv")
    assert (c.imported, c.invalid) == (1, 1)
    j = _import(db, data_dir, "sample_array.json")
    assert (j.imported, j.invalid) == (1, 0)
    art = db.scalar(select(Article).where(Article.canonical_url == "https://example.com/blr-flyover"))
    assert art.source_name == "Deccan Herald" and art.published_at.isoformat() == "2026-09-03T02:30:00"


def test_path_traversal_rejected(data_dir):
    with pytest.raises(PermissionError):
        importer.resolve_safe(str(data_dir / ".." / ".." / "windows" / "win.ini"))
    with pytest.raises(PermissionError):
        importer.resolve_safe("../../etc/passwd.csv")
    with pytest.raises(ValueError):
        importer.sanitize_upload_name("evil.exe")
    assert importer.sanitize_upload_name("../../a b;c.jsonl") == "a_b_c.jsonl"


def test_upload_endpoint(client):
    r = client.post("/api/imports/upload", files={"file": ("../../x.csv", b"title,url\nRoad closed in Thane,https://example.com/thane-closed\n", "text/csv")})
    assert r.status_code == 200, r.text
    assert r.json()["file"] == "x.csv"
    r = client.post("/api/imports/upload", files={"file": ("x.exe", b"MZ", "application/octet-stream")})
    assert r.status_code == 415


def test_import_batches_listed(client):
    r = client.get("/api/imports/batches")
    assert r.status_code == 200 and r.json()["total"] >= 4
