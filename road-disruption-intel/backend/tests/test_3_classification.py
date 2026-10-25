"""Classification schema validation, LLM provider errors, retries, geocoding and incidents."""
import json
from datetime import datetime

import httpx
import pytest
from sqlalchemy import select

from rdi.db.models import Alert, Article, Classification, GeocodeCache, Incident
from rdi.services import incidents, settings_store, text
from rdi.services.classification.classifier import classify_article, human_correction
from rdi.services.classification.schema import extract_json, validate_output
from rdi.services.geo.geocoder import Geocoder, valid_india_coords
from rdi.services.ingest import ArticleIn, Ingestor
from rdi.services.llm.providers import LLMError, build_provider

SRC = "NH-48 closed near Vasai after container truck overturns; traffic diverted via Bhiwandi, police said."


def good_output(**over):
    d = {"relevance": "RELEVANT", "category": "CLOSURE", "summary": "NH-48 closed near Vasai", "country": "India",
         "state": "Maharashtra", "city": "Vasai", "locality": None, "road_name": None, "highway_number": "NH 48",
         "direction": None, "affected_segment": None, "event_start": None, "event_end": None, "time_status": "ONGOING",
         "severity": "HIGH", "reported_delay": None, "advisory_action": "Use Bhiwandi route as advised by police",
         "evidence_excerpt": "NH-48 closed near Vasai after container truck overturns", "confidence": "HIGH",
         "missing_information": ["event end time"]}
    d.update(over)
    return d


def ollama_client(contents, status=200):
    """Mock Ollama /api/chat returning successive contents (or HTTP errors)."""
    seq = list(contents)

    def h(req):
        item = seq.pop(0) if len(seq) > 1 else seq[0]
        if isinstance(item, int):
            return httpx.Response(item, json={"error": "boom"})
        return httpx.Response(status, json={"model": "llama3:8b", "message": {"content": item}})
    return httpx.Client(transport=httpx.MockTransport(h))


def make_article(db, title, url, published=datetime(2026, 9, 8, 6, 0), source="Test News"):
    ing = Ingestor(db, "FILE", "test")
    out = ing.ingest(ArticleIn(title=title, url=url, summary_text=title, source_name=source, published_at=published))
    db.commit()
    return db.get(Article, out.article_id)


# ------------------------------------------------------------------ schema validation
def test_validate_good_output():
    fields, issues, fatal = validate_output(good_output(), SRC, datetime(2026, 9, 8))
    assert not fatal
    assert fields["highway_number"] == "NH-48" and fields["evidence_verified"] is True
    assert fields["model_confidence"] == "HIGH"


def test_validate_rejects_fabrication_and_bad_values():
    out = good_output(category="TRAFFIC_JAM", road_name="Western Express Highway", highway_number="NH 66",
                      event_start="next week sometime", event_end="1999-01-01T00:00:00", latitude=19.1,
                      evidence_excerpt="A sentence that is not in the article at all", confidence=0.3)
    fields, issues, fatal = validate_output(out, SRC, datetime(2026, 9, 8))
    assert not fatal
    assert fields["category"] == "CONGESTION"  # synonym mapped
    assert fields["road_name"] is None and fields["highway_number"] is None  # not in source text -> removed
    assert fields["event_start"] is None and fields["event_end"] is None
    assert fields["evidence_verified"] is False and fields["model_confidence"] == "LOW"
    joined = " ".join(issues)
    assert "not found in the source text" in joined and "not a valid date" in joined and "coordinates ignored" in joined


def test_validate_fatal_on_missing_relevance():
    _, _, fatal = validate_output({"category": "CLOSURE"}, SRC, None)
    assert fatal


def test_extract_json_handles_fences_and_garbage():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Here you go: {"a": 2} thanks') == {"a": 2}
    assert extract_json("no json here") is None
    assert extract_json("[1, 2]") is None


# ------------------------------------------------------------------ providers
def test_provider_config_validation():
    with pytest.raises(LLMError) as e:
        build_provider("not-a-provider", {})
    assert e.value.kind == "CONFIG"
    with pytest.raises(LLMError) as e:
        build_provider("openai_compatible", {"base_url": "https://api.openai.com/v1", "model": "x"}).generate_json("s", "u", {})
    assert e.value.kind == "CONFIG"  # missing key detected before any request
    with pytest.raises(LLMError) as e:
        build_provider("anthropic", {"base_url": "https://api.anthropic.com", "model": "x"}).generate_json("s", "u", {})
    assert e.value.kind == "CONFIG"
    with pytest.raises(LLMError) as e:
        build_provider("ollama", {"base_url": "http://127.0.0.1:11434", "model": ""}).generate_json("s", "u", {})
    assert e.value.kind == "CONFIG"


def test_invalid_api_key_is_auth_error(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-invalid-key-123456")
    c = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(401, json={"error": {"message": "Incorrect API key"}})))
    p = build_provider("openai_compatible", {"base_url": "https://api.openai.com/v1", "model": "gpt-x"}, c)
    with pytest.raises(LLMError) as e:
        p.generate_json("s", "u", {})
    assert e.value.kind == "AUTH" and not e.value.retryable
    assert "sk-test-invalid" not in str(e.value)


def test_quota_exhausted_is_not_retryable(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key-0000000000")
    body = {"error": {"message": "You have no credits remaining. Add credits to continue.", "type": "insufficient_quota"}}
    c = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(429, json=body)))
    with pytest.raises(LLMError) as e:
        build_provider("openai_compatible", {"base_url": "https://api.openai.com/v1", "model": "m"}, c).generate_json("s", "u", {})
    assert e.value.kind == "QUOTA" and not e.value.retryable
    c2 = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(429, json={"error": {"message": "Rate limit reached for requests"}})))
    with pytest.raises(LLMError) as e:
        build_provider("openai_compatible", {"base_url": "https://api.openai.com/v1", "model": "m"}, c2).generate_json("s", "u", {})
    assert e.value.kind == "RATE_LIMIT" and e.value.retryable


def test_anthropic_tool_output_parsed(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-000000000")
    seen = {}

    def h(req):
        seen["headers"] = req.headers
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json={"model": "claude-x", "content": [{"type": "tool_use", "name": "record_road_event", "input": good_output()}]})
    p = build_provider("anthropic", {"base_url": "https://api.anthropic.com", "model": "claude-x"}, httpx.Client(transport=httpx.MockTransport(h)))
    res = p.generate_json("sys", "user", {"type": "object"})
    assert res.parsed["category"] == "CLOSURE"
    assert seen["body"]["tool_choice"]["name"] == "record_road_event" and seen["headers"]["anthropic-version"]


def test_ollama_unavailable_and_model_missing():
    def down(req):
        raise httpx.ConnectError("refused", request=req)
    p = build_provider("ollama", {"base_url": "http://127.0.0.1:9", "model": "llama3:8b"}, httpx.Client(transport=httpx.MockTransport(down)))
    with pytest.raises(LLMError) as e:
        p.generate_json("s", "u", {})
    assert e.value.kind == "UNAVAILABLE" and e.value.retryable
    p = build_provider("ollama", {"base_url": "http://x", "model": "nope:1b"}, httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(404, json={"error": "model not found"}))))
    with pytest.raises(LLMError) as e:
        p.generate_json("s", "u", {})
    assert e.value.kind == "MODEL_NOT_FOUND" and "ollama pull" in str(e.value)


def test_llm_test_endpoint_reports_unreachable(client):
    r = client.put("/api/llm/config", json={"providers": {"ollama": {"base_url": "http://127.0.0.1:9"}}})
    assert r.status_code == 200
    r = client.post("/api/llm/test", json={"provider": "ollama"})
    assert r.status_code == 200 and r.json()["ok"] is False and r.json()["error"]["kind"] in ("UNAVAILABLE", "TIMEOUT")
    client.put("/api/llm/config", json={"providers": {"ollama": {"base_url": "http://127.0.0.1:11434"}}})


# ------------------------------------------------------------------ classification workflow
def test_classification_success_after_retry_and_incident(db, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    art = make_article(db, "NH-48 closed near Vasai after container truck overturns", "https://example.com/vasai-1")
    cls = classify_article(db, art, "ollama", "tester", http_client=ollama_client([500, json.dumps(good_output())]),
                           geocoder=Geocoder(db, online=False))
    db.commit()
    assert cls.status == "VALID" and cls.is_current and cls.provider == "ollama" and cls.model == "llama3:8b"
    assert any("after retry" in i for i in cls.validation_issues)
    assert art.classification_status == "CLASSIFIED" and art.review_status == "PENDING_REVIEW"
    assert cls.geo_status == "APPROXIMATE" and cls.geo_precision == "CITY" and cls.state == "Maharashtra"
    inc = db.get(Incident, art.incident_id)
    assert inc.status == "NEW" and inc.highway_number == "NH-48" and inc.article_count == 1


def test_malformed_output_is_failure_not_success(db, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    art = make_article(db, "Waterlogging at Hindmata junction in Mumbai", "https://example.com/hindmata")
    cls = classify_article(db, art, "ollama", "tester", http_client=ollama_client(["not json", "still not json", "nope"]),
                           geocoder=Geocoder(db, online=False))
    db.commit()
    assert cls.status == "INVALID" and not cls.is_current
    assert art.classification_status == "FAILED" and art.current_classification_id is None and art.incident_id is None
    assert cls.raw_output == "nope"
    # Retry after the provider recovers
    ok = classify_article(db, art, "ollama", "tester",
                          http_client=ollama_client([json.dumps(good_output(category="FLOODING", city="Mumbai", highway_number=None,
                                                                            evidence_excerpt="Waterlogging at Hindmata junction"))]),
                          geocoder=Geocoder(db, online=False))
    db.commit()
    assert ok.status == "VALID" and ok.version == 2 and art.classification_status == "CLASSIFIED"


def test_no_write_lock_held_during_model_call(db):
    """Operators must be able to write (e.g. approve records) while a slow model call is in progress."""
    import sqlite3
    from rdi.config import settings as cfg
    art = make_article(db, "Traffic jam on Ghodbunder Road in Thane", "https://example.com/ghodbunder")
    wrote = {}

    def h(req):
        con = sqlite3.connect(str(cfg.sqlite_path), timeout=1)
        try:
            con.execute("UPDATE app_settings SET updated_at = updated_at")
            con.execute("CREATE TABLE IF NOT EXISTS _lock_probe (x INTEGER)")
            con.commit()
            wrote["ok"] = True
        except sqlite3.OperationalError as e:
            wrote["ok"] = str(e)
        finally:
            con.close()
        return httpx.Response(200, json={"model": "m", "message": {"content": json.dumps(good_output(
            category="CONGESTION", city="Thane", highway_number=None, evidence_excerpt="Traffic jam on Ghodbunder Road"))}})
    cls = classify_article(db, art, "ollama", "tester", http_client=httpx.Client(transport=httpx.MockTransport(h)),
                           geocoder=Geocoder(db, online=False))
    db.commit()
    assert wrote["ok"] is True, wrote["ok"]
    assert cls.status == "VALID"


def test_reclassification_keeps_approval_only_if_outcome_unchanged(db):
    art = make_article(db, "NH-48 closed near Vasai, second report", "https://example.com/vasai-approval")
    run = lambda out: classify_article(db, art, "ollama", "tester", http_client=ollama_client([json.dumps(out)]),  # noqa: E731
                                       geocoder=Geocoder(db, online=False))
    run(good_output(evidence_excerpt="NH-48 closed near Vasai"))
    art.review_status = "APPROVED"
    db.commit()
    run(good_output(evidence_excerpt="NH-48 closed near Vasai", severity="LOW"))  # same relevance/category
    db.commit()
    assert art.review_status == "APPROVED"
    run(good_output(evidence_excerpt="NH-48 closed near Vasai", category="ACCIDENT"))  # outcome changed
    db.commit()
    assert art.review_status == "PENDING_REVIEW"
    from rdi.db.models import AuditLog
    assert db.scalar(select(AuditLog).where(AuditLog.entity_id == art.id, AuditLog.action == "review_cleared")) is not None


def test_city_state_implies_city(db):
    art = make_article(db, "Traffic curbs in Delhi due to protest", "https://example.com/delhi-curbs")
    cls = classify_article(db, art, "ollama", "tester", geocoder=Geocoder(db, online=False), http_client=ollama_client([json.dumps(
        good_output(category="PROTEST", city=None, state="Delhi", highway_number=None, evidence_excerpt="Traffic curbs in Delhi"))]))
    db.commit()
    assert cls.city == "Delhi" and cls.geo_precision == "CITY"


def test_permanent_provider_error_not_retried_forever(db, monkeypatch):
    calls = {"n": 0}

    def h(req):
        calls["n"] += 1
        return httpx.Response(404, json={"error": "model 'x' not found"})
    art = make_article(db, "Traffic diverted for metro work in Pune", "https://example.com/pune-metro")
    settings_store.patch(db, "classification", {"ml_fallback": False})
    try:
        cls = classify_article(db, art, "ollama", "tester", http_client=httpx.Client(transport=httpx.MockTransport(h)),
                               geocoder=Geocoder(db, online=False))
    finally:
        settings_store.patch(db, "classification", {"ml_fallback": True})
    db.commit()
    assert cls.status == "FAILED" and calls["n"] == 1 and "MODEL_NOT_FOUND" in cls.error


def test_separate_accidents_not_merged_but_same_closure_linked(db):
    a1 = make_article(db, "Two killed in crash on NH-48 near Vasai", "https://example.com/acc1", source="A")
    a2 = make_article(db, "Bike accident in Andheri, one injured", "https://example.com/acc2", source="B")
    for a, loc, hw in ((a1, None, "NH-48"), (a2, "Andheri", None)):
        c = Classification(id=text.new_id("CLS_"), article_id=a.id, status="VALID", relevance="RELEVANT", category="ACCIDENT",
                           city="Mumbai", state="Maharashtra", locality=loc, highway_number=hw, severity="HIGH", time_status="ONGOING")
        db.add(c)
        db.flush()
        incidents.link_article(db, a, c)
    db.commit()
    assert a1.incident_id and a2.incident_id and a1.incident_id != a2.incident_id

    a3 = make_article(db, "NH-48 still blocked near Vasai, long queues", "https://example.com/acc3", source="C",
                      published=datetime(2026, 9, 8, 9, 0))
    c3 = Classification(id=text.new_id("CLS_"), article_id=a3.id, status="VALID", relevance="RELEVANT", category="ACCIDENT",
                        city="Mumbai", state="Maharashtra", highway_number="NH-48", severity="LOW", time_status="ONGOING")
    db.add(c3)
    db.flush()
    incidents.link_article(db, a3, c3)
    db.commit()
    inc = db.get(Incident, a1.incident_id)
    assert a3.incident_id == a1.incident_id and inc.article_count == 2
    assert inc.has_conflict and any("Severity disagreement" in n for n in inc.conflict_notes)


def test_status_transitions_alerts_and_resolution(db):
    art = make_article(db, "Mumbai-Pune Expressway shut after landslide near Khandala", "https://example.com/ls1")
    c = Classification(id=text.new_id("CLS_"), article_id=art.id, status="VALID", relevance="RELEVANT", category="LANDSLIDE",
                       city="Lonavala", state="Maharashtra", road_name="Mumbai-Pune Expressway", severity="CRITICAL", time_status="ONGOING")
    db.add(c)
    db.flush()
    art.current_classification_id = c.id
    inc = incidents.link_article(db, art, c)
    with pytest.raises(ValueError):
        incidents.transition(db, inc, "NEW")  # same status is a no-op, but invalid targets raise
        incidents.transition(db, inc, "BOGUS")
    with pytest.raises(ValueError):
        incidents.transition(db, inc, "BOGUS")
    incidents.on_article_review(db, art, "APPROVED", "op")
    db.commit()
    assert inc.status == "CONFIRMED" and inc.last_verified_at is not None
    alerts = db.scalars(select(Alert).where(Alert.incident_id == inc.id)).all()
    assert len(alerts) == 1
    incidents.maybe_alert(db, inc)  # deduplicated
    assert len(db.scalars(select(Alert).where(Alert.incident_id == inc.id)).all()) == 1

    # A later report saying the road reopened resolves it, preserving history.
    art2 = make_article(db, "Mumbai-Pune Expressway reopened after landslide debris cleared", "https://example.com/ls2",
                        published=datetime(2026, 9, 8, 20, 0))
    c2 = Classification(id=text.new_id("CLS_"), article_id=art2.id, status="VALID", relevance="RELEVANT", category="LANDSLIDE",
                        city="Lonavala", state="Maharashtra", road_name="Mumbai-Pune Expressway", severity="LOW", time_status="RESOLVED")
    db.add(c2)
    db.flush()
    incidents.link_article(db, art2, c2)
    db.commit()
    assert inc.status == "RESOLVED" and inc.article_count == 2
    with pytest.raises(ValueError):
        incidents.transition(db, inc, "NEW")
    incidents.transition(db, inc, "MONITORING", "op", "re-check")
    db.commit()
    assert inc.status == "MONITORING"


def test_human_correction_creates_new_version(db):
    art = make_article(db, "Flooding closes Sion road in Mumbai", "https://example.com/sion")
    c = Classification(id=text.new_id("CLS_"), article_id=art.id, status="VALID", relevance="RELEVANT", category="FLOODING",
                       city="Mumbai", state="Maharashtra", severity="MODERATE", version=1, is_current=True, origin="MODEL",
                       provider="ollama", model="m")
    db.add(c)
    art.current_classification_id = c.id
    db.flush()
    new = human_correction(db, art, {"severity": "HIGH", "latitude": 19.04, "longitude": 72.86}, "qa", "checked")
    db.commit()
    assert new.origin == "HUMAN" and new.version == 2 and new.is_current and not db.get(Classification, c.id).is_current
    assert new.geo_status == "MANUAL" and new.severity == "HIGH"
    with pytest.raises(ValueError):
        human_correction(db, art, {"latitude": 51.5, "longitude": -0.1}, "qa")  # outside India
    with pytest.raises(ValueError):
        human_correction(db, art, {"category": "ALIENS"}, "qa")


# ------------------------------------------------------------------ geocoding
def test_geocoder_cache_and_failures(db):
    calls = {"n": 0}

    def ok(req):
        calls["n"] += 1
        return httpx.Response(200, json=[{"lat": "19.1197", "lon": "72.8468", "display_name": "Andheri, Mumbai"}])
    g = Geocoder(db, client=httpx.Client(transport=httpx.MockTransport(ok)), online=True)
    r1 = g.resolve("Andheri", "Bombay", None)
    r2 = g.resolve("Andheri", "Mumbai", "Maharashtra")
    assert r1.precision == "LOCALITY" and r1.method == "NOMINATIM" and r1.status == "APPROXIMATE"
    assert r2.latitude == r1.latitude
    assert calls["n"] == 2 or calls["n"] == 1  # query strings differ only by state context
    before = calls["n"]
    g.resolve("Andheri", "Mumbai", "Maharashtra")
    assert calls["n"] == before  # served from cache
    assert db.scalar(select(GeocodeCache).where(GeocodeCache.status == "OK")) is not None

    def far(req):
        return httpx.Response(200, json=[{"lat": "28.6", "lon": "77.2", "display_name": "Delhi"}])
    r = Geocoder(db, client=httpx.Client(transport=httpx.MockTransport(far)), online=True).resolve("Some Nagar", "Mumbai", None)
    assert r.precision == "CITY" and r.method == "GAZETTEER"  # far-away match rejected, falls back to city centroid

    def boom(req):
        raise httpx.ConnectError("down", request=req)
    r = Geocoder(db, client=httpx.Client(transport=httpx.MockTransport(boom)), online=True).resolve("Kothrud", "Pune", None)
    assert r.precision == "CITY" and r.status == "APPROXIMATE"

    assert Geocoder(db, online=False).resolve(None, None, "Kerala").precision == "STATE"
    assert Geocoder(db, online=False).resolve(None, "Atlantis", None).status == "UNRESOLVED"
    assert not valid_india_coords(51.5, -0.1) and not valid_india_coords("x", None) and valid_india_coords(19.0, 72.8)


def test_settings_store_merge(db):
    settings_store.patch(db, "incidents", {"stale_after_hours": 48})
    cfg = settings_store.get(db, "incidents")
    assert cfg["stale_after_hours"] == 48 and "link_window_hours" in cfg
    settings_store.patch(db, "incidents", {"stale_after_hours": 72})
    db.commit()
