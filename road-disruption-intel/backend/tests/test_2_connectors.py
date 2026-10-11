"""Connector parsing and error handling with saved fixtures and mocked HTTP."""
import httpx
import pytest

from rdi.db.models import Source
from rdi.services.acquisition import run_source
from rdi.services.connectors import ConnectorError
from rdi.services.connectors.apis import GDELTConnector, NewsAPIConnector
from rdi.services.connectors.base import http_get
from rdi.services.connectors.feeds import GoogleNewsRSSConnector
from conftest import FIXTURES

NOSLEEP = lambda s: None  # noqa: E731


def _src(**kw):
    base = dict(id="t", name="t", connector_type="x", enabled=True, config={}, max_retries=2, timeout_seconds=5,
                poll_interval_minutes=60, max_records=50)
    base.update(kw)
    return Source(**base)


def mock(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_google_news_rss_parsing():
    calls = []

    def h(req):
        calls.append(req)
        return httpx.Response(200, content=(FIXTURES / "google_news.xml").read_bytes())
    conn = GoogleNewsRSSConnector(_src(config={"terms": ["road closed"], "places": ["Mumbai"], "queries_per_run": 1}), mock(h), NOSLEEP)
    res = conn.fetch(10)
    assert len(res.items) == 2 and not res.errors
    first = res.items[0]
    assert first.source_name == "Mid-day" and first.published_at.isoformat() == "2026-10-05T04:10:00"
    assert "when:3d" in str(calls[0].url.params["q"])
    assert res.state_updates["_cursor"] == 0  # rotation wraps around a single combination


def test_gdelt_parsing_and_rate_limit():
    ok = GDELTConnector(_src(config={"terms": ['"road closed"']}), mock(lambda r: httpx.Response(200, content=(FIXTURES / "gdelt.json").read_bytes())), NOSLEEP)
    res = ok.fetch(10)
    assert len(res.items) == 1 and res.items[0].published_at.isoformat() == "2026-10-06T10:15:00"
    limited = GDELTConnector(_src(config={"terms": ['"a"']}, max_retries=1), mock(lambda r: httpx.Response(429, text="Please limit requests")), NOSLEEP)
    res = limited.fetch(10)
    assert res.partial and not res.items and "429" in res.errors[0]


def test_retry_on_5xx_then_success():
    n = {"c": 0}

    def h(req):
        n["c"] += 1
        return httpx.Response(503) if n["c"] < 3 else httpx.Response(200, text="ok")
    r = http_get(mock(h), "https://x.test", retries=3, sleep=NOSLEEP)
    assert r.status_code == 200 and n["c"] == 3


def test_auth_failure_not_retried():
    n = {"c": 0}

    def h(req):
        n["c"] += 1
        return httpx.Response(401)
    with pytest.raises(ConnectorError) as e:
        http_get(mock(h), "https://x.test", retries=5, sleep=NOSLEEP)
    assert e.value.kind == "AUTH" and n["c"] == 1


def test_timeout_is_bounded():
    def h(req):
        raise httpx.ReadTimeout("slow", request=req)
    with pytest.raises(ConnectorError) as e:
        http_get(mock(h), "https://x.test", retries=2, sleep=NOSLEEP)
    assert e.value.kind == "TIMEOUT"


def test_newsapi_not_configured_without_key():
    st, msg = NewsAPIConnector(_src()).configuration_status()
    assert st == "NOT_CONFIGURED" and "NEWSAPI_KEY" in msg


def test_run_source_records_health_and_isolates_failures(db, monkeypatch):
    rss = (FIXTURES / "google_news.xml").read_bytes()
    src = db.get(Source, "google_news_india")
    src.config = {**src.config, "terms": ["road closed"], "places": ["Mumbai"], "queries_per_run": 1}
    db.commit()
    run = run_source(db, "google_news_india", client=mock(lambda r: httpx.Response(200, content=rss)), sleep=NOSLEEP)
    assert run.status == "OK" and run.new == 2
    run2 = run_source(db, "google_news_india", client=mock(lambda r: httpx.Response(200, content=rss)), sleep=NOSLEEP)
    assert run2.new == 0 and run2.duplicates == 2  # dedup across fetch runs
    src = db.get(Source, "google_news_india")
    assert src.total_new == 2 and src.last_success_at is not None and src.next_run_at is not None

    # A connector that crashes must not raise out of run_source.
    from rdi.services.connectors import feeds
    monkeypatch.setattr(feeds.GoogleNewsRSSConnector, "fetch", lambda self, limit: 1 / 0)
    bad = run_source(db, "google_news_india", sleep=NOSLEEP)
    assert bad.status == "ERROR" and "ZeroDivisionError" in bad.error
    assert db.get(Source, "google_news_india").consecutive_failures == 1

    # Unconfigured source reports NOT_CONFIGURED instead of fetching.
    nc = run_source(db, "newsapi", sleep=NOSLEEP)
    assert nc.status == "NOT_CONFIGURED"
