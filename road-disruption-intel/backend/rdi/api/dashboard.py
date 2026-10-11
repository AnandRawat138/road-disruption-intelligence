"""Dashboard, data-quality and summary-report endpoints. Every number is a live database query."""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from ..db.models import (Alert, Article, ArticleSighting, Classification, FetchRun, ImportBatch, Incident, Job,
                         Source, utcnow)
from ..db.session import get_db
from ..services import incidents as inc_svc, settings_store
from .common import iso, parse_date_param, row_dict

router = APIRouter(tags=["dashboard"])

DEFINITIONS = {
    "total_source_records": "Every row/item ever received from files or connectors, including repeats of the same article.",
    "unique_articles": "Distinct articles after URL/ID/content deduplication.",
    "relevant_reports": "Articles whose current classification is RELEVANT (model or human).",
    "unclassified": "Articles never successfully classified (includes those not yet queued).",
    "failed_classifications": "Articles whose only classification attempts failed or produced invalid output.",
    "awaiting_review": "Classified articles waiting for operator approval or rejection.",
    "active_incidents": "Incidents in NEW/MONITORING/CONFIRMED status with a report within the staleness window.",
    "stale_open_incidents": "Open incidents with no new report within the staleness window – treat as unverified.",
    "recently_resolved": "Incidents moved to RESOLVED in the last 7 days.",
    "high_severity_active": "Active incidents with HIGH or CRITICAL severity.",
    "last_successful_refresh": "Most recent successful fetch from any live source.",
}


def _rel_filters(date_from, date_to, state, category):
    conds = [Classification.is_current.is_(True), Classification.relevance == "RELEVANT"]
    if date_from:
        conds.append(Article.published_at >= parse_date_param(date_from))
    if date_to:
        conds.append(Article.published_at <= parse_date_param(date_to, end_of_day=True))
    if state:
        conds.append(Classification.state == state)
    if category:
        conds.append(Classification.category == category)
    return and_(*conds)


@router.get("/api/dashboard/summary")
def summary(date_from: str | None = None, date_to: str | None = None, state: str | None = None,
            category: str | None = None, db: Session = Depends(get_db)):
    now = utcnow()
    stale_h = int(settings_store.get(db, "incidents").get("stale_after_hours", 72))
    cutoff = now - timedelta(hours=stale_h)
    active_cond = and_(Incident.status.in_(inc_svc.ACTIVE_STATUSES), Incident.last_reported_at >= cutoff)
    inc_filter = []
    if state:
        inc_filter.append(Incident.state == state)
    if category:
        inc_filter.append(Incident.category == category)

    def count(q):
        return db.scalar(q) or 0

    rel = _rel_filters(date_from, date_to, state, category)
    joined = select(func.count(Article.id)).join(Classification, Classification.id == Article.current_classification_id)
    metrics = {
        "total_source_records": count(select(func.count(ArticleSighting.id))),
        "unique_articles": count(select(func.count(Article.id)).where(Article.near_duplicate_of.is_(None))),
        "relevant_reports": count(joined.where(rel)),
        "unclassified": count(select(func.count(Article.id)).where(Article.classification_status.in_(("UNCLASSIFIED", "QUEUED", "PROCESSING")))),
        "failed_classifications": count(select(func.count(Article.id)).where(Article.classification_status == "FAILED")),
        "awaiting_review": count(select(func.count(Article.id)).where(Article.review_status == "PENDING_REVIEW")),
        "active_incidents": count(select(func.count(Incident.id)).where(active_cond, *inc_filter)),
        "stale_open_incidents": count(select(func.count(Incident.id)).where(
            Incident.status.in_(inc_svc.ACTIVE_STATUSES), or_(Incident.last_reported_at < cutoff,
                                                               Incident.last_reported_at.is_(None)), *inc_filter)),
        "recently_resolved": count(select(func.count(Incident.id)).where(
            Incident.status == "RESOLVED", Incident.updated_at >= now - timedelta(days=7), *inc_filter)),
        "high_severity_active": count(select(func.count(Incident.id)).where(
            active_cond, Incident.severity.in_(("HIGH", "CRITICAL")), *inc_filter)),
        "total_incidents": count(select(func.count(Incident.id)).where(*inc_filter) if inc_filter else select(func.count(Incident.id))),
        "classified": count(select(func.count(Article.id)).where(Article.current_classification_id.is_not(None))),
    }
    last_refresh = db.scalar(select(func.max(Source.last_success_at)))

    def dist(col, n=15):
        q = (select(col, func.count()).select_from(Article)
             .join(Classification, Classification.id == Article.current_classification_id)
             .where(rel, col.is_not(None)).group_by(col).order_by(func.count().desc()).limit(n))
        return [{"key": k, "count": c} for k, c in db.execute(q)]

    # Daily volume over the selected range (default: last 60 days of data present)
    d_to = parse_date_param(date_to, end_of_day=True) if date_to else now
    d_from = parse_date_param(date_from) if date_from else d_to - timedelta(days=60)
    day = func.date(Article.published_at)
    timeline_rel = dict(db.execute(select(day, func.count()).select_from(Article)
                                   .join(Classification, Classification.id == Article.current_classification_id)
                                   .where(rel, Article.published_at.between(d_from, d_to)).group_by(day)).all())
    timeline_all = dict(db.execute(select(day, func.count()).where(Article.published_at.between(d_from, d_to),
                                                                   Article.near_duplicate_of.is_(None))
                                   .group_by(day)).all())
    days = sorted(set(timeline_all) | set(timeline_rel))
    timeline = [{"date": d, "articles": timeline_all.get(d, 0), "relevant": timeline_rel.get(d, 0)} for d in days]

    prefilter = [{"key": k or "NONE", "count": c} for k, c in db.execute(
        select(Article.prefilter_label, func.count()).where(Article.classification_status == "UNCLASSIFIED")
        .group_by(Article.prefilter_label))]
    coverage = db.execute(select(func.min(Article.published_at), func.max(Article.published_at))).one()

    sources = []
    for s in db.scalars(select(Source).order_by(Source.name)):
        sources.append({"id": s.id, "name": s.name, "enabled": s.enabled, "last_status": s.last_status,
                        "last_success_at": iso(s.last_success_at), "last_attempt_at": iso(s.last_attempt_at),
                        "last_error": (s.last_error or "")[:200] or None, "total_new": s.total_new})
    runs = [row_dict(r, exclude={"details"}) for r in db.scalars(select(FetchRun).order_by(FetchRun.started_at.desc()).limit(8))]
    imports = [{"id": b.id, "file_name": b.file_name, "status": b.status, "finished_at": iso(b.finished_at),
                "imported": b.imported, "duplicate": b.duplicate, "invalid": b.invalid, "failed": b.failed,
                "discovered": b.discovered}
               for b in db.scalars(select(ImportBatch).order_by(ImportBatch.created_at.desc()).limit(8))]
    recent_cls = db.execute(select(Classification.created_at, Classification.provider, Classification.model,
                                   Classification.status, Classification.relevance, Classification.category,
                                   Article.title, Article.id)
                            .join(Article, Article.id == Classification.article_id)
                            .order_by(Classification.created_at.desc()).limit(8)).all()
    cls_24h = dict(db.execute(select(Classification.status, func.count()).where(
        Classification.created_at >= now - timedelta(hours=24)).group_by(Classification.status)).all())
    jobs = [{"id": j.id, "job_type": j.job_type, "status": j.status, "message": j.message, "processed": j.processed,
             "total": j.total, "created_at": iso(j.created_at)}
            for j in db.scalars(select(Job).order_by(Job.created_at.desc()).limit(6))]
    unread_alerts = db.scalar(select(func.count(Alert.id)).where(Alert.read_at.is_(None))) or 0
    return {
        "generated_at": iso(now), "filters": {"date_from": date_from, "date_to": date_to, "state": state, "category": category},
        "metrics": metrics, "definitions": DEFINITIONS, "stale_after_hours": stale_h,
        "last_successful_refresh": iso(last_refresh),
        "coverage": {"earliest_published": iso(coverage[0]), "latest_published": iso(coverage[1])},
        "by_category": dist(Classification.category), "by_state": dist(Classification.state),
        "by_city": dist(Classification.city, 12), "by_severity": dist(Classification.severity),
        "timeline": timeline, "unclassified_by_prefilter": prefilter, "sources": sources, "recent_fetch_runs": runs,
        "recent_imports": imports,
        "recent_classifications": [{"at": iso(r[0]), "provider": r[1], "model": r[2], "status": r[3], "relevance": r[4],
                                    "category": r[5], "title": r[6], "article_id": r[7]} for r in recent_cls],
        "classifications_24h": cls_24h, "recent_jobs": jobs, "unread_alerts": unread_alerts,
    }


@router.get("/api/quality")
def data_quality(db: Session = Depends(get_db)):
    now = utcnow()
    cur = and_(Classification.is_current.is_(True), Classification.relevance == "RELEVANT")
    base = select(func.count(Classification.id)).where(cur)
    stale_h = int(settings_store.get(db, "incidents").get("stale_after_hours", 72))

    def c(q):
        return db.scalar(q) or 0

    missing = {
        "city": c(base.where(Classification.city.is_(None))),
        "state": c(base.where(Classification.state.is_(None))),
        "road_or_highway": c(base.where(Classification.road_name.is_(None), Classification.highway_number.is_(None))),
        "event_start": c(base.where(Classification.event_start.is_(None))),
        "severity": c(base.where(or_(Classification.severity.is_(None), Classification.severity == "UNKNOWN"))),
        "evidence_unverified": c(base.where(Classification.evidence_verified.is_not(True))),
    }
    geo = {
        "unresolved": c(base.where(Classification.geo_status == "UNRESOLVED")),
        "state_level_only": c(base.where(Classification.geo_precision == "STATE")),
        "city_level": c(base.where(Classification.geo_precision == "CITY")),
        "locality_level": c(base.where(Classification.geo_precision == "LOCALITY")),
        "manual": c(base.where(Classification.geo_precision == "MANUAL")),
        "invalid_coordinates": c(base.where(Classification.latitude.is_not(None), or_(
            Classification.latitude < 6, Classification.latitude > 37.6,
            Classification.longitude < 68, Classification.longitude > 97.5))),
    }
    stale_cut = now - timedelta(hours=stale_h)
    stale_open = db.scalars(select(Incident).where(Incident.status.in_(inc_svc.ACTIVE_STATUSES),
                                                   Incident.last_reported_at < stale_cut)
                            .order_by(Incident.last_reported_at.desc()).limit(20)).all()
    conflicts = db.scalars(select(Incident).where(Incident.has_conflict.is_(True)).order_by(Incident.updated_at.desc()).limit(20)).all()
    failed = db.execute(select(Article.id, Article.title, Article.classification_attempts).where(
        Article.classification_status == "FAILED").limit(20)).all()
    date_issues = c(select(func.count(Classification.id)).where(cur, Classification.event_end.is_not(None),
                                                                 Classification.event_start.is_not(None),
                                                                 Classification.event_end < Classification.event_start))

    # Source reliability from measured outcomes (classification and operator review), not assumptions.
    rel_rows = db.execute(
        select(Article.source_name, func.count(Article.id),
               func.sum(case((Classification.relevance == "RELEVANT", 1), else_=0)),
               func.sum(case((Article.review_status == "APPROVED", 1), else_=0)),
               func.sum(case((Article.review_status == "REJECTED", 1), else_=0)))
        .join(Classification, Classification.id == Article.current_classification_id)
        .group_by(Article.source_name).having(func.count(Article.id) >= 3)
        .order_by(func.count(Article.id).desc()).limit(30)).all()
    reliability = [{"source": s or "unknown", "classified": n, "relevant": r or 0,
                    "relevant_rate": round((r or 0) / n, 3) if n else None, "approved": ap or 0, "rejected": rj or 0,
                    "approval_rate": round((ap or 0) / ((ap or 0) + (rj or 0)), 3) if (ap or 0) + (rj or 0) else None}
                   for s, n, r, ap, rj in rel_rows]

    # Possible duplicate incidents: same category + city, reported within 48h, not yet merged.
    a, b = Incident.__table__.alias("a"), Incident.__table__.alias("b")
    dup_rows = db.execute(select(a.c.id, a.c.title, b.c.id, b.c.title, a.c.city, a.c.category).where(
        a.c.id < b.c.id, a.c.category == b.c.category, func.lower(a.c.city) == func.lower(b.c.city),
        a.c.status != "DISMISSED", b.c.status != "DISMISSED",
        func.abs(func.julianday(a.c.last_reported_at) - func.julianday(b.c.last_reported_at)) <= 2).limit(30)).all()
    return {
        "generated_at": iso(now), "relevant_records": c(base), "missing_fields": missing, "geocoding": geo,
        "date_conflicts": date_issues,
        "stale_open_incidents": [{"id": i.id, "title": i.title, "last_reported_at": iso(i.last_reported_at)} for i in stale_open],
        "conflicting_incidents": [{"id": i.id, "title": i.title, "notes": i.conflict_notes} for i in conflicts],
        "failed_classifications": [{"id": r[0], "title": r[1], "attempts": r[2]} for r in failed],
        "failed_total": c(select(func.count(Article.id)).where(Article.classification_status == "FAILED")),
        "source_reliability": reliability,
        "duplicate_suggestions": [{"a_id": r[0], "a_title": r[1], "b_id": r[2], "b_title": r[3], "city": r[4],
                                   "category": r[5]} for r in dup_rows],
    }


@router.get("/api/reports/summary")
def summary_report(date_from: str = Query(...), date_to: str = Query(...), state: str | None = None,
                   db: Session = Depends(get_db)):
    d_from, d_to = parse_date_param(date_from), parse_date_param(date_to, end_of_day=True)
    conds = [Incident.last_reported_at >= d_from, Incident.first_reported_at <= d_to]
    if state:
        conds.append(Incident.state == state)
    incs = db.scalars(select(Incident).where(*conds, Incident.status != "DISMISSED")
                      .order_by(Incident.last_reported_at.desc())).all()
    by = lambda attr: sorted(((k, sum(1 for i in incs if getattr(i, attr) == k)) for k in {getattr(i, attr) for i in incs}),  # noqa: E731
                             key=lambda x: -x[1])
    sev_rank = inc_svc.SEVERITY_RANK
    top = sorted(incs, key=lambda i: (-sev_rank.get(i.severity or "UNKNOWN", 0), -(i.article_count or 0)))[:25]
    art_q = select(func.count(Article.id)).where(Article.published_at.between(d_from, d_to))
    rel_q = (select(func.count(Article.id)).join(Classification, Classification.id == Article.current_classification_id)
             .where(Article.published_at.between(d_from, d_to), Classification.relevance == "RELEVANT"))
    approved = db.scalar(select(func.count(Article.id)).where(Article.published_at.between(d_from, d_to),
                                                              Article.review_status == "APPROVED")) or 0
    unclassified = db.scalar(select(func.count(Article.id)).where(
        Article.published_at.between(d_from, d_to), Article.current_classification_id.is_(None))) or 0
    return {
        "generated_at": iso(utcnow()), "period": {"from": iso(d_from), "to": iso(d_to)}, "state": state,
        "articles_in_period": db.scalar(art_q) or 0, "relevant_in_period": db.scalar(rel_q) or 0,
        "approved_in_period": approved, "unclassified_in_period": unclassified,
        "incident_count": len(incs),
        "by_category": [{"key": k, "count": v} for k, v in by("category")],
        "by_state": [{"key": k or "Unknown", "count": v} for k, v in by("state")],
        "by_severity": [{"key": k or "UNKNOWN", "count": v} for k, v in by("severity")],
        "by_status": [{"key": k, "count": v} for k, v in by("status")],
        "top_incidents": [row_dict(i) for i in top],
        "provenance": ("Generated from the local database. Incidents are derived from news reports classified by an "
                       "LLM and, where indicated, reviewed by an operator. Unclassified articles in the period are not "
                       "represented in incident counts. Locations are approximate centroids."),
    }
