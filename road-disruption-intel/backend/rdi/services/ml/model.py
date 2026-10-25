"""Local machine-learning classifier (TF-IDF features + logistic regression).

It is used when the operator selects the ML engine, and as the automatic
fallback when the selected LLM provider cannot be reached. Three models are
trained from labelled records:

* relevance   – RELEVANT vs not relevant
* category    – event category of relevant records
* time status – UPCOMING / ONGOING / RESOLVED / UNKNOWN of relevant records

Training labels come from the current, valid LLM and human classifications in
the database (human corrections and approved records weigh more; rejected
records and the ML model's own outputs are never used), from a bundled seed set
of labelled headlines, and from weak negatives – unclassified articles that the
keyword pre-filter rates as unlikely. Reported metrics are cross-validated
agreement with these labels, not accuracy against verified ground truth.

The ML model never asserts severity or event times: it has no grounded way to
read them, so they stay UNKNOWN / empty and are listed as missing.
"""
from __future__ import annotations

import json
import logging
import random
import re
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...config import settings
from ...db.models import Article, Classification, utcnow
from ..geo.gazetteer_data import ALIASES, CITIES, STATE_ALIASES, STATES
from ..highways import mask_highway_names, primary_highway_number, primary_named_road
from ..text import normalize_title, strip_publisher_suffix

log = logging.getLogger(__name__)

ML_PROMPT_VERSION = "ml-v1"
SEED_FILE = Path(__file__).with_name("seed_labels.jsonl")
MIN_PER_CLASS = 5          # categories with fewer examples are not learned
MIN_RELEVANT, MIN_NOT_RELEVANT = 30, 30
HUMAN_WEIGHT = 3.0
_lock = threading.Lock()
_cache: dict = {"mtime": None, "model": None}


class MLUnavailable(Exception):
    """The ML model cannot be trained or loaded."""


def model_path() -> Path:
    return settings.runtime_dir / "models" / "ml_classifier.joblib"


@dataclass
class TrainingRow:
    text: str
    relevance: str            # RELEVANT / NOT_RELEVANT
    category: str | None
    time_status: str | None
    weight: float
    origin: str               # db_model / db_human / seed / weak_negative


def model_text(title: str | None, summary: str | None = None, source: str | None = None) -> str:
    t = strip_publisher_suffix(title or "", source).strip()
    s = re.sub(r"\s+", " ", summary or "").strip()
    if s and len(s) > 20:
        nt, ns = normalize_title(t), normalize_title(s)
        if not (ns.startswith(nt) or nt.startswith(ns)):  # Google News summaries repeat the headline
            t = f"{t}. {s[:600]}"
    return t


# ----------------------------------------------------------------------------- training data
def _db_rows(db: Session) -> list[TrainingRow]:
    rows: list[TrainingRow] = []
    q = select(Article, Classification).join(Classification, Classification.id == Article.current_classification_id) \
        .where(Classification.status == "VALID", Classification.provider != "ml",
               Article.review_status != "REJECTED", Classification.relevance.in_(("RELEVANT", "RELATED", "IRRELEVANT")))
    for art, cls in db.execute(q):
        human = cls.origin == "HUMAN" or art.review_status == "APPROVED"
        rows.append(TrainingRow(model_text(art.title, art.summary_text, art.source_name),
                                "RELEVANT" if cls.relevance == "RELEVANT" else "NOT_RELEVANT",
                                cls.category, cls.time_status, HUMAN_WEIGHT if human else 1.0,
                                "db_human" if human else "db_model"))
    return rows


def _weak_negatives(db: Session, n: int, exclude: set[str]) -> list[TrainingRow]:
    ids = list(db.scalars(select(Article.id).where(Article.prefilter_label == "UNLIKELY",
                                                   Article.current_classification_id.is_(None)).limit(50000)))
    random.Random(42).shuffle(ids)
    out: list[TrainingRow] = []
    for i in range(0, len(ids), 500):
        for art in db.scalars(select(Article).where(Article.id.in_(ids[i:i + 500]))):
            text = model_text(art.title, art.summary_text, art.source_name)
            key = normalize_title(text)
            if text and key not in exclude:
                exclude.add(key)
                out.append(TrainingRow(text, "NOT_RELEVANT", None, None, 1.0, "weak_negative"))
            if len(out) >= n:
                return out
    return out


def _seed_rows(exclude: set[str]) -> list[TrainingRow]:
    if not SEED_FILE.is_file():
        return []
    out = []
    with open(SEED_FILE, encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            r = json.loads(line)
            key = normalize_title(r["text"])
            if key in exclude:
                continue
            exclude.add(key)
            weak = "weak negative" in (r.get("label_source") or "")
            out.append(TrainingRow(r["text"], r["relevance"], r.get("category"), r.get("time_status"), 1.0,
                                   "weak_negative" if weak else "seed"))
    return out


def training_rows(db: Session) -> list[TrainingRow]:
    rows = [r for r in _db_rows(db) if r.text]
    seen = {normalize_title(r.text) for r in rows}
    rows += _seed_rows(seen)
    n_rel = sum(1 for r in rows if r.relevance == "RELEVANT")
    n_not = len(rows) - n_rel
    if n_not < 2 * n_rel:
        rows += _weak_negatives(db, max(0, 2 * n_rel - n_not), seen)
    return rows


# ----------------------------------------------------------------------------- model
def _pipeline():
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import FeatureUnion, Pipeline
    from sklearn.feature_extraction.text import TfidfVectorizer
    feats = FeatureUnion([
        ("word", TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, strip_accents="unicode", min_df=1)),
        ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True, min_df=2)),
    ])
    return Pipeline([("features", feats),
                     ("clf", LogisticRegression(max_iter=3000, C=5.0, class_weight="balanced"))])


def _evaluate(texts: list[str], labels: list[str], mask: list[bool] | None = None) -> dict:
    """Stratified k-fold cross-validated agreement with the training labels."""
    from collections import Counter
    from sklearn.metrics import accuracy_score, f1_score
    from sklearn.model_selection import StratifiedKFold, cross_val_predict
    counts = Counter(labels)
    k = min(5, min(counts.values()))
    if k < 2 or len(counts) < 2:
        return {"evaluated": False, "reason": "too few examples per class", "n": len(labels)}
    pred = cross_val_predict(_pipeline(), texts, labels, cv=StratifiedKFold(k, shuffle=True, random_state=42))
    majority = counts.most_common(1)[0][1] / len(labels)
    out = {"evaluated": True, "folds": k, "n": len(labels), "accuracy": round(accuracy_score(labels, pred), 4),
           "macro_f1": round(f1_score(labels, pred, average="macro"), 4), "majority_baseline": round(majority, 4),
           "classes": dict(counts)}
    if mask is not None and any(mask):
        y = [l for l, m in zip(labels, mask) if m]
        p = [x for x, m in zip(pred, mask) if m]
        out["labelled_only"] = {"n": len(y), "accuracy": round(accuracy_score(y, p), 4),
                                "macro_f1": round(f1_score(y, p, average="macro"), 4)}
    return out


def train(db: Session, actor: str = "system") -> dict:
    """Train all three models, evaluate them by cross-validation and save them to runtime/models."""
    import joblib
    import sklearn
    rows = training_rows(db)
    rel = [r for r in rows if r.relevance == "RELEVANT"]
    if len(rel) < MIN_RELEVANT or len(rows) - len(rel) < MIN_NOT_RELEVANT:
        raise MLUnavailable(f"Not enough labelled records to train (relevant {len(rel)}, not relevant "
                            f"{len(rows) - len(rel)}; need {MIN_RELEVANT} of each)")
    started = utcnow()
    models, metrics = {}, {}

    texts, labels, weights = [r.text for r in rows], [r.relevance for r in rows], [r.weight for r in rows]
    metrics["relevance"] = _evaluate(texts, labels, [r.origin != "weak_negative" for r in rows])
    models["relevance"] = _pipeline().fit(texts, labels, clf__sample_weight=weights)

    for target in ("category", "time_status"):
        data = [r for r in rel if getattr(r, target)]
        from collections import Counter
        counts = Counter(getattr(r, target) for r in data)
        data = [r for r in data if counts[getattr(r, target)] >= MIN_PER_CLASS]
        if len({getattr(r, target) for r in data}) < 2:
            models[target] = None
            metrics[target] = {"evaluated": False, "reason": "fewer than two classes with enough examples"}
            continue
        t, y, w = [r.text for r in data], [getattr(r, target) for r in data], [r.weight for r in data]
        metrics[target] = _evaluate(t, y)
        metrics[target]["not_learned"] = sorted(k for k, v in counts.items() if v < MIN_PER_CLASS)
        models[target] = _pipeline().fit(t, y, clf__sample_weight=w)

    from collections import Counter
    version = f"tfidf-logreg-{started:%Y%m%d%H%M%S}"
    meta = {"version": version, "trained_at": started.isoformat(timespec="seconds"), "trained_by": actor,
            "sklearn_version": sklearn.__version__, "training_rows": len(rows),
            "by_origin": dict(Counter(r.origin for r in rows)),
            "relevant_rows": len(rel), "metrics": metrics,
            "method": "TF-IDF word 1-2-grams + character 3-5-grams, logistic regression (class-balanced)",
            "metric_note": "Cross-validated agreement with the training labels (mostly LLM labels), "
                           "not accuracy against verified ground truth."}
    path = model_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    joblib.dump({"models": models, "meta": meta}, tmp)
    tmp.replace(path)
    path.with_suffix(".json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    with _lock:
        _cache.update(mtime=None, model=None)
    log.info("Trained ML classifier %s on %d rows", version, len(rows))
    return meta


def load() -> dict | None:
    path = model_path()
    if not path.is_file():
        return None
    mtime = path.stat().st_mtime
    with _lock:
        if _cache["mtime"] == mtime and _cache["model"] is not None:
            return _cache["model"]
        try:
            import joblib
            bundle = joblib.load(path)
        except Exception as e:  # incompatible library version, corrupted file …
            log.warning("Cannot load ML model %s: %s", path, e)
            return None
        _cache.update(mtime=mtime, model=bundle)
        return bundle


def ensure_model(db: Session) -> dict:
    bundle = load()
    if bundle is not None:
        return bundle
    try:
        train(db, actor="auto")
    except MLUnavailable:
        raise
    except ImportError as e:
        raise MLUnavailable("scikit-learn is not installed – run setup_and_start.bat again") from e
    bundle = load()
    if bundle is None:
        raise MLUnavailable("The ML model could not be loaded after training")
    return bundle


def status() -> dict:
    path = model_path()
    meta_file = path.with_suffix(".json")
    meta = json.loads(meta_file.read_text(encoding="utf-8")) if meta_file.is_file() else None
    try:
        import sklearn
        sk = sklearn.__version__
    except ImportError:
        sk = None
    return {"trained": path.is_file() and meta is not None, "model": meta, "sklearn_installed": sk is not None,
            "sklearn_version": sk, "seed_labels": SEED_FILE.is_file()}


# ----------------------------------------------------------------------------- prediction
_CITY_NAMES = sorted({*CITIES, *ALIASES}, key=len, reverse=True)
_CITY_RE = re.compile(r"(?<![A-Za-z])(" + "|".join(re.escape(c) for c in _CITY_NAMES) + r")(?![A-Za-z])", re.I)
_STATE_NAMES = sorted({*STATES, *STATE_ALIASES}, key=len, reverse=True)
_STATE_RE = re.compile(r"(?<![A-Za-z])(" + "|".join(re.escape(s) for s in _STATE_NAMES) + r")(?![A-Za-z])", re.I)
_ROAD_RE = re.compile(r"\b((?:[A-Z][A-Za-z.]+\s){1,3}(?:Road|Marg|Flyover|Bridge|Bypass|Salai|Link Road|Ghat))\b")


def _proba(model, text: str) -> tuple[str, float, dict]:
    probs = model.predict_proba([text])[0]
    classes = list(model.classes_)
    best = max(range(len(classes)), key=lambda i: probs[i])
    return classes[best], float(probs[best]), {c: round(float(p), 4) for c, p in zip(classes, probs)}


def predict_output(bundle: dict, title: str, text: str, threshold: float = 0.6) -> tuple[dict, dict]:
    """Return (output dict in the LLM output format, probability details)."""
    models = bundle["models"]
    label, _p, rel_probs = _proba(models["relevance"], text)
    p_rel = rel_probs.get("RELEVANT", 0.0)
    lower = max(0.0, threshold - 0.2)
    relevance = "RELEVANT" if p_rel >= threshold else "NEEDS_REVIEW" if p_rel >= lower else "IRRELEVANT"
    details: dict = {"relevance": rel_probs}
    category, time_status, p_cat = "UNKNOWN", "UNKNOWN", 0.0
    if relevance != "IRRELEVANT":
        if models.get("category") is not None:
            category, p_cat, details["category"] = _proba(models["category"], text)
        if models.get("time_status") is not None:
            time_status, _, details["time_status"] = _proba(models["time_status"], text)
    p_rel_side = p_rel if relevance != "IRRELEVANT" else 1.0 - p_rel
    combined = p_rel_side * (p_cat if relevance != "IRRELEVANT" and p_cat else 1.0)
    confidence = "HIGH" if combined >= 0.7 else "MEDIUM" if combined >= 0.45 else "LOW"

    places = mask_highway_names(text)  # "Mumbai-Goa highway near Ratnagiri" -> city Ratnagiri, not Mumbai
    m_city = _CITY_RE.search(places)
    m_state = _STATE_RE.search(places)
    m_road = _ROAD_RE.search(text)
    out = {
        "relevance": relevance, "category": category, "time_status": time_status, "severity": "UNKNOWN",
        "summary": title, "evidence_excerpt": title, "confidence": confidence,
        "country": "India" if relevance != "IRRELEVANT" else None,
        "state": m_state.group(1) if m_state else None, "city": m_city.group(1) if m_city else None,
        "locality": None, "highway_number": primary_highway_number(text),
        "road_name": primary_named_road(text) or (m_road.group(1) if m_road else None),
        "event_start": None, "event_end": None, "direction": None, "affected_segment": None,
        "reported_delay": None, "advisory_action": None,
        "missing_information": ["severity", "event_start", "event_end"] + ([] if m_city else ["city"]),
    }
    details["combined_confidence"] = round(combined, 4)
    return out, details
