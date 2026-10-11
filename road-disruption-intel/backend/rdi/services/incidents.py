"""Incident lifecycle: linking related reports, status transitions, conflicts and alerts.

Linking is deliberately conservative so that separate events are not merged:
reports are linked only when category and city agree, they fall within the
link window, and – where either report names a specific road, highway or
locality – those specifics also agree.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db.models import Alert, Article, Classification, Incident, IncidentHistory, utcnow
from . import audit, settings_store
from .classification.schema import appears_in
from .text import new_id

log = logging.getLogger(__name__)

ACTIVE_STATUSES = ("NEW", "MONITORING", "CONFIRMED")
STATUSES = ("NEW", "MONITORING", "CONFIRMED", "RESOLVED", "DISMISSED")
TRANSITIONS = {
    "NEW": {"MONITORING", "CONFIRMED", "RESOLVED", "DISMISSED"},
    "MONITORING": {"CONFIRMED", "RESOLVED", "DISMISSED"},
    "CONFIRMED": {"MONITORING", "RESOLVED", "DISMISSED"},
    "RESOLVED": {"MONITORING", "CONFIRMED"},
    "DISMISSED": {"NEW"},
}
SEVERITY_RANK = {"UNKNOWN": 0, "LOW": 1, "MODERATE": 2, "HIGH": 3, "CRITICAL": 4}
PRECISION_RANK = {None: 0, "STATE": 1, "CITY": 2, "LOCALITY": 3, "MANUAL": 4}
# Categories that describe an area-wide situation; reports without specific
# roads may be linked by city. Point events (accidents, closures …) may not.
AREA_CATEGORIES = {"FLOODING", "WEATHER", "SECURITY_VIP", "PROTEST", "CONGESTION"}


def _report_time(article: Article, cls: Classification) -> datetime | None:
    return cls.event_start or article.published_at or article.ingested_at


def _specifics(obj) -> dict:
    return {"highway": obj.highway_number, "road": obj.road_name, "locality": obj.locality}


def _specifics_agree(a: dict, b: dict) -> bool | None:
    """True if they share a specific, False if both specific but disjoint, None if not comparable."""
    if a["highway"] and b["highway"]:
        return a["highway"] == b["highway"]
    shared = False
    comparable = False
    for key in ("road", "locality"):
        if a[key] and b[key]:
            comparable = True
            if appears_in(a[key], b[key]) or appears_in(b[key], a[key]):
                shared = True
    if comparable:
        return shared
    return None


def find_match(db: Session, article: Article, cls: Classification, window_hours: int) -> Incident | None:
    if not cls.city or not cls.category or cls.category in ("UNKNOWN", "OTHER"):
        return None
    t = _report_time(article, cls)
    q = select(Incident).where(Incident.category == cls.category, Incident.status != "DISMISSED",
                               func.lower(Incident.city) == cls.city.lower())
    if t is not None:
        lo, hi = t - timedelta(hours=window_hours), t + timedelta(hours=window_hours)
        q = q.where(or_(Incident.last_reported_at.is_(None),
                        Incident.last_reported_at.between(lo, hi),
                        Incident.first_reported_at.between(lo, hi)))
    mine = _specifics(cls)
    for inc in db.scalars(q.order_by(Incident.last_reported_at.desc()).limit(25)):
        agree = _specifics_agree(mine, _specifics(inc))
        if agree is True:
            return inc
        if agree is None and cls.category in AREA_CATEGORIES and not any(mine.values()) and not any(_specifics(inc).values()):
            return inc
    return None


def _set_status(db: Session, inc: Incident, to: str, actor: str, note: str | None) -> None:
    if inc.status == to:
        return
    db.add(IncidentHistory(incident_id=inc.id, from_status=inc.status, to_status=to, actor=actor, note=note))
    audit.record(db, "incident", inc.id, "status_change", actor, old=inc.status, new=to, note=note)
    inc.status = to
    if to == "CONFIRMED":
        inc.last_verified_at = utcnow()
    inc.updated_at = utcnow()
    maybe_alert(db, inc)


def transition(db: Session, inc: Incident, to: str, actor: str = "operator", note: str | None = None) -> Incident:
    to = to.upper()
    if to not in STATUSES:
        raise ValueError(f"Unknown status {to}")
    if to == inc.status:
        return inc
    if to not in TRANSITIONS.get(inc.status, set()):
        raise ValueError(f"Cannot change status from {inc.status} to {to}")
    _set_status(db, inc, to, actor, note)
    return inc


def _apply_geo(inc: Incident, cls: Classification) -> None:
    if cls.latitude is None or cls.geo_status == "UNRESOLVED":
        return
    if PRECISION_RANK.get(cls.geo_precision, 0) > PRECISION_RANK.get(inc.geo_precision, 0) or inc.latitude is None:
        inc.latitude, inc.longitude, inc.geo_precision = cls.latitude, cls.longitude, cls.geo_precision


def link_article(db: Session, article: Article, cls: Classification, actor: str = "system") -> Incident | None:
    """Attach a RELEVANT classified article to an existing or new incident."""
    if cls.relevance != "RELEVANT" or cls.status != "VALID":
        detach_article(db, article, actor, "classification no longer relevant")
        return None
    cfg = settings_store.get(db, "incidents")
    if article.incident_id:
        current = db.get(Incident, article.incident_id)
        if current is not None and current.category == cls.category and (current.city or "").lower() == (cls.city or "").lower():
            refresh_incident(db, current)
            return current
        detach_article(db, article, actor, "re-linked after reclassification")

    inc = find_match(db, article, cls, int(cfg.get("link_window_hours", 72)))
    t = _report_time(article, cls)
    if inc is None:
        inc = Incident(id=new_id("INC_"), title=(cls.summary or article.title)[:300], category=cls.category,
                       severity=cls.severity, status="NEW", time_status=cls.time_status, state=cls.state,
                       city=cls.city, locality=cls.locality, road_name=cls.road_name,
                       highway_number=cls.highway_number, first_reported_at=t, last_reported_at=t,
                       event_start=cls.event_start, event_end=cls.event_end, article_count=0, conflict_notes=[])
        db.add(inc)
        db.flush()
        db.add(IncidentHistory(incident_id=inc.id, from_status=None, to_status="NEW", actor=actor,
                               note=f"Created from article {article.id}"))
    else:
        _merge_into(db, inc, article, cls, actor, cfg)
    article.incident_id = inc.id
    _apply_geo(inc, cls)
    db.flush()
    refresh_incident(db, inc)
    return inc


def _merge_into(db: Session, inc: Incident, article: Article, cls: Classification, actor: str, cfg: dict) -> None:
    notes = list(inc.conflict_notes or [])
    s_new, s_old = SEVERITY_RANK.get(cls.severity or "UNKNOWN", 0), SEVERITY_RANK.get(inc.severity or "UNKNOWN", 0)
    if s_new and s_old and abs(s_new - s_old) >= 2:
        notes.append(f"Severity disagreement: {inc.severity} vs {cls.severity} (article {article.id})")
    if s_new > s_old:
        inc.severity = cls.severity
    if cls.event_start and inc.event_start and abs(cls.event_start - inc.event_start) > timedelta(hours=48):
        notes.append(f"Start-time disagreement: {inc.event_start:%Y-%m-%d %H:%M} vs {cls.event_start:%Y-%m-%d %H:%M} UTC "
                     f"(article {article.id})")
    if cls.event_end and (inc.event_end is None or cls.event_end > inc.event_end):
        inc.event_end = cls.event_end
    for key in ("highway_number", "road_name", "locality", "state"):
        if getattr(inc, key) is None and getattr(cls, key):
            setattr(inc, key, getattr(cls, key))

    if cls.time_status == "RESOLVED" and inc.status in ACTIVE_STATUSES and cfg.get("auto_resolve_on_report", True):
        _set_status(db, inc, "RESOLVED", "system", f"Reported resolved by article {article.id}")
    elif cls.time_status in ("ONGOING", "UPCOMING") and inc.status == "RESOLVED":
        notes.append(f"Article {article.id} reports the event as {cls.time_status} after it was marked resolved")
        _set_status(db, inc, "MONITORING", "system", f"Re-opened for review: conflicting report {article.id}")
    if cls.time_status not in (None, "UNKNOWN"):
        inc.time_status = cls.time_status
    if notes != list(inc.conflict_notes or []):
        inc.conflict_notes = notes[-20:]
        inc.has_conflict = True


def detach_article(db: Session, article: Article, actor: str, reason: str) -> None:
    if not article.incident_id:
        return
    inc = db.get(Incident, article.incident_id)
    article.incident_id = None
    db.flush()
    if inc is not None:
        refresh_incident(db, inc)
        if inc.article_count == 0 and inc.status != "DISMISSED":
            _set_status(db, inc, "DISMISSED", actor, f"No remaining evidence ({reason})")


def refresh_incident(db: Session, inc: Incident) -> None:
    """Recompute counts and time bounds from linked, non-rejected articles."""
    rows = db.execute(select(Article.published_at, Article.ingested_at).where(
        Article.incident_id == inc.id, Article.review_status != "REJECTED")).all()
    inc.article_count = len(rows)
    times = [p or i for p, i in rows if (p or i)]
    if times:
        inc.first_reported_at = min(times + ([inc.first_reported_at] if inc.first_reported_at else []))
        inc.last_reported_at = max(times)
    inc.updated_at = utcnow()


def on_article_review(db: Session, article: Article, decision: str, actor: str) -> None:
    """Approval confirms the incident; rejection removes the article's evidence."""
    if not article.incident_id:
        return
    inc = db.get(Incident, article.incident_id)
    if inc is None:
        return
    if decision == "APPROVED":
        inc.last_verified_at = utcnow()
        if inc.status in ("NEW", "MONITORING"):
            _set_status(db, inc, "CONFIRMED", actor, f"Article {article.id} approved by operator")
    elif decision == "REJECTED":
        refresh_incident(db, inc)
        if inc.article_count == 0 and inc.status != "DISMISSED":
            _set_status(db, inc, "DISMISSED", actor, "All linked articles rejected")


def is_stale(inc: Incident, stale_hours: int, now: datetime | None = None) -> bool:
    now = now or utcnow()
    ref = inc.last_reported_at or inc.created_at
    return ref is not None and (now - ref) > timedelta(hours=stale_hours)


def maybe_alert(db: Session, inc: Incident) -> None:
    cfg = settings_store.get(db, "alerts")
    if not cfg.get("enabled"):
        return
    if inc.status not in (cfg.get("on_status") or ["CONFIRMED"]):
        return
    if SEVERITY_RANK.get(inc.severity or "UNKNOWN", 0) < SEVERITY_RANK.get(cfg.get("min_severity", "HIGH"), 3):
        return
    cats = cfg.get("categories") or []
    if cats and inc.category not in cats:
        return
    key = f"{inc.id}:{inc.status}:{cfg.get('min_severity')}"
    if db.scalar(select(Alert.id).where(Alert.dedup_key == key)):
        return
    try:
        with db.begin_nested():
            db.add(Alert(incident_id=inc.id, rule=f"status={inc.status},severity>={cfg.get('min_severity')}",
                         message=f"{inc.severity} {inc.category} incident {inc.status.lower()}: {inc.title[:140]}",
                         severity=inc.severity, dedup_key=key))
    except IntegrityError:
        pass
