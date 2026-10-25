"""Highway extraction and listing, the ML classifier, engine selection and the LLM -> ML fallback."""
from datetime import timedelta

import httpx
import pytest
from sqlalchemy import select

from rdi.db.models import Article, Classification, Incident, utcnow
from rdi.services import settings_store
from rdi.services.classification.classifier import classify_article
from rdi.services.geo.geocoder import Geocoder
from rdi.services.highways import extract_highways, primary_highway_number
from rdi.services.ml import model as ml

from test_3_classification import make_article


# ------------------------------------------------------------------ highway extraction
@pytest.mark.parametrize("text,expected", [
    ("NH-48 closed near Vapi; traffic diverted via SH 10", ["NH-48", "SH-10"]),
    ("National Highway 66 stretch shut after landslide", ["NH-66"]),
    ("NHAI to repair NH44 potholes", ["NH-44"]),
    ("Traffic Jam On Mumbai-Pune Expressway After Accident", ["Mumbai-Pune Expressway"]),
    ("Missing Link on Mumbai-Pune Expressway opens", ["Mumbai-Pune Expressway"]),
    ("Landslide blocks Chandigarh-Manali highway", ["Chandigarh-Manali Highway"]),
    ("Waterlogging on Western Express Highway", ["Western Express Highway"]),
    ("Why Noida Expressway Is Jammed Again", ["Noida Expressway"]),
    ("NHAI announces new toll policy", []),
    ("Sensex rises 300 points", []),
])
def test_extract_highways(text, expected):
    assert [r.name.split(" (")[0] for r in extract_highways(text)] == expected


def test_highway_aliases_share_one_id():
    a = extract_highways("Pune-Mumbai Expressway jam")[0]
    b = extract_highways("Mumbai-Pune Expressway closed")[0]
    c = extract_highways("Delhi-Gurgaon Expressway")[0]
    assert a.id == b.id and c.name == "Delhi-Gurugram Expressway"
    assert primary_highway_number("Traffic hit on NH 9 and Delhi-Meerut Expressway") == "NH-9"


def test_highways_api_lists_running_stale_and_unverified(client, db):
    now = utcnow()
    inc = Incident(id="INC_HWYTEST1", title="Truck overturns on NH-48 near Vapi", category="ACCIDENT", severity="HIGH",
                   status="NEW", time_status="ONGOING", state="Gujarat", city="Vapi", highway_number="NH-48",
                   first_reported_at=now, last_reported_at=now, article_count=1, conflict_notes=[])
    old = Incident(id="INC_HWYTEST2", title="Landslide on Mumbai-Goa highway", category="LANDSLIDE", status="NEW",
                   time_status="ONGOING", state="Maharashtra", city="Ratnagiri", first_reported_at=now - timedelta(days=9),
                   last_reported_at=now - timedelta(days=9), article_count=1, conflict_notes=[])
    done = Incident(id="INC_HWYTEST3", title="NH-48 reopened", category="CLOSURE", status="RESOLVED",
                    time_status="RESOLVED", city="Vapi", highway_number="NH-48", last_reported_at=now,
                    article_count=1, conflict_notes=[])
    db.add_all([inc, old, done])
    art = make_article(db, "Traffic snarl on Yamuna Expressway after pile-up", "https://example.com/yamuna-hwy",
                       published=now - timedelta(hours=3))
    art.prefilter_label = "LIKELY_RELEVANT"
    db.commit()

    r = client.get("/api/highways").json()
    by_name = {i["name"]: i for i in r["items"]}
    assert by_name["NH-48"]["running_incidents"] == 1          # resolved incident is not counted
    assert by_name["Mumbai-Goa Highway"]["stale_incidents"] == 1
    assert by_name["Yamuna Expressway"]["unverified_reports"] == 1
    assert r["items"][0]["name"] == "NH-48"                     # running incidents sort first
    assert client.get("/api/highways", params={"include_stale": "false"}).json()["total"] == r["total"] - 1
    assert [i["name"] for i in client.get("/api/highways", params={"q": "yamuna"}).json()["items"]] == ["Yamuna Expressway"]

    d = client.get("/api/highways/detail", params={"id": "NH-48"}).json()
    ids = [i["id"] for i in d["incidents"]]
    assert ids[0] == "INC_HWYTEST1" and "INC_HWYTEST3" not in ids and d["highway"]["max_severity"] == "HIGH"
    assert all(i["is_stale"] for i in d["incidents"][1:])  # other NH-48 incidents from earlier tests are old
    assert client.get("/api/highways/detail", params={"id": "NH-9999"}).status_code == 404


# ------------------------------------------------------------------ ML classifier
@pytest.fixture(scope="module")
def trained(_database):
    from rdi.db.session import SessionLocal
    with SessionLocal() as s:
        meta = ml.train(s, actor="test")
        s.commit()
    return meta


def test_ml_training_reports_honest_metrics(trained):
    assert trained["training_rows"] >= 1000 and trained["relevant_rows"] >= 300
    rel = trained["metrics"]["relevance"]
    assert rel["evaluated"] and rel["accuracy"] > rel["majority_baseline"]
    assert "labelled_only" in rel and "not accuracy against verified ground truth" in trained["metric_note"]
    assert ml.status()["trained"] and ml.model_path().is_file()


def test_ml_predictions_are_grounded(trained):
    bundle = ml.load()
    out, details = ml.predict_output(bundle, "NH-48 closed near Vasai after landslide, traffic diverted",
                                     "NH-48 closed near Vasai after landslide, traffic diverted")
    assert out["relevance"] == "RELEVANT" and out["highway_number"] == "NH-48" and out["city"] == "Vasai"
    assert out["severity"] == "UNKNOWN" and out["event_start"] is None  # never asserted by the ML model
    t = "Landslide blocks Mumbai-Goa highway near Ratnagiri, traffic halted"
    hw, _ = ml.predict_output(bundle, t, t)
    assert hw["city"] == "Ratnagiri" and hw["state"] is None and hw["road_name"] == "Mumbai-Goa Highway"
    neg, _ = ml.predict_output(bundle, "Sensex rises 300 points as IT stocks gain", "Sensex rises 300 points as IT stocks gain")
    assert neg["relevance"] == "IRRELEVANT"


def test_ml_engine_classifies_and_links_incident(db, trained):
    art = make_article(db, "Waterlogging on Western Express Highway in Mumbai after heavy rain",
                       "https://example.com/ml-engine-1")
    cls = classify_article(db, art, actor="tester", engine="ml", geocoder=Geocoder(db, online=False))
    db.commit()
    assert cls.status == "VALID" and cls.provider == "ml" and cls.model.startswith("tfidf-logreg-")
    assert cls.relevance == "RELEVANT" and cls.city == "Mumbai" and cls.evidence_verified
    assert cls.road_name == "Western Express Highway" and art.incident_id is not None


def test_llm_unavailable_falls_back_to_ml(db, trained, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)

    def down(req):
        raise httpx.ConnectError("connection refused")
    art = make_article(db, "Traffic diverted on NH-48 near Vasai for bridge repair", "https://example.com/ml-fallback-1")
    cls = classify_article(db, art, "ollama", "tester", http_client=httpx.Client(transport=httpx.MockTransport(down)),
                           geocoder=Geocoder(db, online=False))
    db.commit()
    assert cls.provider == "ml" and cls.status == "VALID" and cls.is_current
    assert any("ML fallback" in i for i in cls.validation_issues)
    attempts = db.scalars(select(Classification).where(Classification.article_id == art.id)
                          .order_by(Classification.version)).all()
    assert [(c.provider, c.status) for c in attempts] == [("ollama", "FAILED"), ("ml", "VALID")]


def test_engine_setting_and_ml_api(client, trained):
    assert client.put("/api/settings/classification", json={"engine": "bert"}).status_code == 422
    assert client.put("/api/settings/classification", json={"ml_relevance_threshold": 2}).status_code == 422
    assert client.put("/api/settings/classification", json={"engine": "ml"}).json()["engine"] == "ml"
    st = client.get("/api/ml/status").json()
    assert st["engine"] == "ml" and st["trained"] and st["ml_fallback"] is True
    r = client.post("/api/ml/test", json={"title": "Landslide blocks Mumbai-Goa highway, traffic halted"}).json()
    assert r["ok"] and r["provider"] == "ml" and r["fields"]["relevance"] in ("RELEVANT", "NEEDS_REVIEW")
    assert "relevance" in r["probabilities"]
    job = client.post("/api/classification/run", json={"article_ids": ["does-not-exist"]}).json()
    assert job["engine"] == "ml" and job["provider"] == "ml"
    client.put("/api/settings/classification", json={"engine": "llm"})


class _Ctx:
    """Minimal stand-in for JobContext when calling a job handler directly."""
    def __init__(self):
        self.messages = []

    def update(self, **kw):
        if kw.get("message"):
            self.messages.append(kw["message"])

    def cancelled(self):
        return False


def test_classify_job_switches_to_ml_when_llm_unreachable(db, trained):
    from rdi.services.job_handlers import _classify
    arts = [make_article(db, t, f"https://example.com/job-fallback-{i}") for i, t in enumerate(
        ["Landslide blocks Mumbai-Goa highway near Ratnagiri", "Sensex closes higher on IT gains"])]
    settings_store.patch(db, "llm", {"providers": {"ollama": {"base_url": "http://127.0.0.1:9"}}})
    db.commit()
    try:
        out = _classify(_Ctx(), {"article_ids": [a.id for a in arts], "reclassify": True, "actor": "tester"})
    finally:
        settings_store.patch(db, "llm", {"providers": {"ollama": {"base_url": "http://127.0.0.1:11434"}}})
        db.commit()
    assert out["_status"] == "COMPLETED" and "using ML fallback" in out["message"] and out["failed"] == 0
    db.expire_all()
    for a in arts:
        cls = db.get(Classification, db.get(Article, a.id).current_classification_id)
        assert cls.provider == "ml" and any("ML fallback" in i for i in cls.validation_issues)
