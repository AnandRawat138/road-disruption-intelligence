"""Highway-specific view: highways named in reports of possibly running events."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import Article, Incident
from ..db.session import get_db
from ..services import highways as hw_svc, settings_store
from .common import iso
from .incidents import incident_row

router = APIRouter(tags=["highways"])

TYPES = ("NATIONAL_HIGHWAY", "STATE_HIGHWAY", "EXPRESSWAY", "NAMED_HIGHWAY")
_SEV = {"UNKNOWN": 0, "LOW": 1, "MODERATE": 2, "HIGH": 3, "CRITICAL": 4}


def _params(report_days: int, include_reports: bool, include_stale: bool) -> dict:
    return {"report_days": report_days, "include_reports": include_reports, "include_stale": include_stale}


@router.get("/api/highways")
def list_highways(q: str | None = Query(default=None, max_length=100), type: str | None = None,
                  report_days: int = Query(default=7, ge=1, le=3650), include_reports: bool = True,
                  include_stale: bool = True, sort: str = "activity", db: Session = Depends(get_db)):
    """Every highway with at least one possibly running event, with counts by evidence type."""
    buckets = hw_svc.collect(db, **_params(report_days, include_reports, include_stale))
    items = [hw_svc.summarize(b) for b in buckets.values()]
    if q:
        needle = q.strip().lower().replace(" ", "")
        items = [i for i in items if needle in i["name"].lower().replace(" ", "")
                 or needle in i["id"].lower() or any(needle in s.lower() for s in i["states"] + i["cities"])]
    if type:
        wanted = {t.strip().upper() for t in type.split(",") if t.strip()}
        items = [i for i in items if i["type"] in wanted]
    keys = {
        "activity": lambda i: (-i["running_incidents"], -i["stale_incidents"], -i["unverified_reports"], i["name"]),
        "severity": lambda i: (-_SEV.get(i["max_severity"], 0), -i["total"], i["name"]),
        "recent": lambda i: (-(i["last_reported_at"].timestamp() if i["last_reported_at"] else 0), i["name"]),
        "name": lambda i: i["name"],
    }
    items.sort(key=keys.get(sort, keys["activity"]))
    for i in items:
        i["last_reported_at"] = iso(i["last_reported_at"])
    stale_hours = int(settings_store.get(db, "incidents").get("stale_after_hours", 72))
    return {"items": items, "total": len(items),
            "meta": {"report_days": report_days, "include_reports": include_reports, "include_stale": include_stale,
                     "stale_after_hours": stale_hours,
                     "by_type": {t: sum(1 for i in items if i["type"] == t) for t in TYPES},
                     "with_running_incidents": sum(1 for i in items if i["running_incidents"]),
                     "note": ("Highways are listed only where a report names them. Running = active incident "
                              f"reported within the last {stale_hours} h; stale = active but not re-reported since; "
                              "unverified = recent unclassified report flagged by the keyword pre-filter.")}}


@router.get("/api/highways/detail")
def highway_detail(id: str = Query(min_length=2, max_length=200), report_days: int = Query(default=7, ge=1, le=3650),
                   include_reports: bool = True, include_stale: bool = True, db: Session = Depends(get_db)):
    buckets = hw_svc.collect(db, **_params(report_days, include_reports, include_stale))
    b = buckets.get(id)
    if b is None:
        raise HTTPException(404, "No possibly running event names this highway")
    stale_hours = int(settings_store.get(db, "incidents").get("stale_after_hours", 72))
    incs = db.scalars(select(Incident).where(Incident.id.in_(b["incident_ids"]))
                      .order_by(Incident.last_reported_at.desc().nullslast())).all()
    incidents = [incident_row(i, stale_hours) for i in incs]
    incidents.sort(key=lambda r: (r["is_stale"], -_SEV.get(r.get("severity") or "UNKNOWN", 0)))
    reports = []
    if b["report_ids"]:
        arts = db.scalars(select(Article).where(Article.id.in_(b["report_ids"][:200]))
                          .order_by(Article.published_at.desc().nullslast())).all()
        reports = [{"id": a.id, "title": a.title, "source_name": a.source_name, "source_url": a.source_url,
                    "published_at": iso(a.published_at), "prefilter_label": a.prefilter_label,
                    "classification_status": a.classification_status, "query_city": a.query_city} for a in arts]
    features = [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [i.longitude, i.latitude]},
                 "properties": {"id": i.id, "title": i.title, "severity": i.severity, "category": i.category,
                                "status": i.status, "geo_precision": i.geo_precision}}
                for i in incs if i.latitude is not None and i.geo_precision in ("CITY", "LOCALITY", "MANUAL")]
    summary = hw_svc.summarize(b)
    summary["last_reported_at"] = iso(summary["last_reported_at"])
    return {"highway": summary, "incidents": incidents, "reports": reports,
            "map": {"type": "FeatureCollection", "features": features},
            "location_note": "Map points are approximate city/locality centroids of the incidents, "
                             "not positions on the highway."}
