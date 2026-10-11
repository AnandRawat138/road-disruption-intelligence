"""Incidents (grouped events), map GeoJSON and incident lifecycle API."""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from ..db.models import Article, Classification, Incident, IncidentHistory, utcnow
from ..db.session import get_db
from ..services import audit, incidents as inc_svc, settings_store
from .common import Page, actor_from, iso, page_envelope, parse_date_param, row_dict, split_csv

router = APIRouter(tags=["incidents"])

SEV_ORDER = case({"CRITICAL": 4, "HIGH": 3, "MODERATE": 2, "LOW": 1}, value=Incident.severity, else_=0)
SORTS = {"last_reported_at": Incident.last_reported_at, "first_reported_at": Incident.first_reported_at,
         "severity": SEV_ORDER, "article_count": Incident.article_count, "city": Incident.city,
         "category": Incident.category, "updated_at": Incident.updated_at}


def incident_filters(request: Request) -> dict:
    qp = request.query_params
    f: dict = {}
    for key in ("q", "state", "city", "highway", "date_from", "date_to", "lifecycle", "has_conflict", "source",
                "classification", "precision"):
        if qp.get(key) not in (None, ""):
            f[key] = qp.get(key)
    for key in ("status", "category", "severity"):
        vals = split_csv(qp.get(key))
        if vals:
            f[key] = vals
    return f


def apply_incident_filters(q, f: dict, stale_hours: int):
    conds = []
    if f.get("q"):
        like = f"%{str(f['q'])[:200]}%"
        conds.append(or_(Incident.title.ilike(like), Incident.city.ilike(like), Incident.road_name.ilike(like),
                         Incident.highway_number.ilike(like), Incident.locality.ilike(like), Incident.state.ilike(like)))
    for key, col in (("status", Incident.status), ("category", Incident.category), ("severity", Incident.severity)):
        if f.get(key):
            conds.append(col.in_(f[key]))
    if f.get("state"):
        conds.append(func.lower(Incident.state) == str(f["state"]).lower())
    if f.get("city"):
        conds.append(func.lower(Incident.city) == str(f["city"]).lower())
    if f.get("highway"):
        conds.append(Incident.highway_number == str(f["highway"]).upper())
    if f.get("date_from"):
        conds.append(Incident.last_reported_at >= parse_date_param(f["date_from"]))
    if f.get("date_to"):
        conds.append(Incident.first_reported_at <= parse_date_param(f["date_to"], end_of_day=True))
    cutoff = utcnow() - timedelta(hours=stale_hours)
    lifecycle = f.get("lifecycle")
    if lifecycle == "active":
        conds.append(Incident.status.in_(inc_svc.ACTIVE_STATUSES))
        conds.append(Incident.last_reported_at >= cutoff)
    elif lifecycle == "stale":
        conds.append(Incident.status.in_(inc_svc.ACTIVE_STATUSES))
        conds.append(or_(Incident.last_reported_at < cutoff, Incident.last_reported_at.is_(None)))
    elif lifecycle == "open":
        conds.append(Incident.status.in_(inc_svc.ACTIVE_STATUSES))
    elif lifecycle == "resolved":
        conds.append(Incident.status == "RESOLVED")
    if f.get("has_conflict") in ("true", "1"):
        conds.append(Incident.has_conflict.is_(True))
    if f.get("precision") == "city_or_better":
        conds.append(Incident.geo_precision.in_(("CITY", "LOCALITY", "MANUAL")))
    if f.get("source"):
        sub = select(Article.incident_id).where(Article.source_name == f["source"], Article.incident_id.is_not(None))
        conds.append(Incident.id.in_(sub))
    if f.get("classification") == "approved":
        sub = select(Article.incident_id).where(Article.review_status == "APPROVED", Article.incident_id.is_not(None))
        conds.append(Incident.id.in_(sub))
    elif f.get("classification") == "pending":
        sub = select(Article.incident_id).where(Article.review_status == "PENDING_REVIEW", Article.incident_id.is_not(None))
        conds.append(Incident.id.in_(sub))
    if conds:
        q = q.where(and_(*conds))
    return q


def incident_row(i: Incident, stale_hours: int) -> dict:
    d = row_dict(i)
    d["is_active"] = i.status in inc_svc.ACTIVE_STATUSES
    d["is_stale"] = d["is_active"] and inc_svc.is_stale(i, stale_hours)
    d["location_note"] = {"LOCALITY": "Approximate – locality centroid", "CITY": "Approximate – city centroid",
                          "STATE": "Approximate – state centroid only", "MANUAL": "Placed by operator"}.get(
        i.geo_precision or "", "Location not resolved")
    return d


@router.get("/api/incidents")
def list_incidents(request: Request, page: Page = Depends(), sort: str = "last_reported_at", order: str = "desc",
                   db: Session = Depends(get_db)):
    stale = int(settings_store.get(db, "incidents").get("stale_after_hours", 72))
    f = incident_filters(request)
    total = db.scalar(apply_incident_filters(select(func.count(Incident.id)), f, stale))
    col = SORTS.get(sort, Incident.last_reported_at)
    q = apply_incident_filters(select(Incident), f, stale).order_by(
        col.asc().nullslast() if order == "asc" else col.desc().nullslast(), Incident.id)
    items = [incident_row(i, stale) for i in db.scalars(q.offset(page.offset).limit(page.page_size))]
    return page_envelope(items, total or 0, page)


@router.get("/api/incidents/export")
def export_incidents(request: Request, format: str = "csv", db: Session = Depends(get_db)):
    stale = int(settings_store.get(db, "incidents").get("stale_after_hours", 72))
    f = incident_filters(request)
    rows = [incident_row(i, stale) for i in db.scalars(apply_incident_filters(select(Incident), f, stale)
                                                       .order_by(Incident.last_reported_at.desc()).limit(20000))]
    stamp = utcnow().strftime("%Y%m%d_%H%M")
    if format == "json":
        body = json.dumps({"generated_at": iso(utcnow()), "filters": f, "count": len(rows), "incidents": rows},
                          ensure_ascii=False)
        return StreamingResponse(iter([body]), media_type="application/json",
                                 headers={"Content-Disposition": f'attachment; filename="rdi_incidents_{stamp}.json"'})
    cols = ["id", "title", "category", "severity", "status", "is_stale", "time_status", "state", "city", "locality",
            "road_name", "highway_number", "latitude", "longitude", "geo_precision", "location_note",
            "first_reported_at", "last_reported_at", "last_verified_at", "event_start", "event_end", "article_count",
            "has_conflict"]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([f"# Incidents export generated {iso(utcnow())}; filters={json.dumps(f)}"])
    w.writerow(cols)
    for r in rows:
        w.writerow(["" if r.get(c) is None else r.get(c) for c in cols])
    return StreamingResponse(iter(["﻿" + buf.getvalue()]), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": f'attachment; filename="rdi_incidents_{stamp}.csv"'})


@router.get("/api/incidents/{incident_id}")
def get_incident(incident_id: str, db: Session = Depends(get_db)):
    i = db.get(Incident, incident_id)
    if i is None:
        raise HTTPException(404, "Incident not found")
    stale = int(settings_store.get(db, "incidents").get("stale_after_hours", 72))
    rows = db.execute(select(Article, Classification).outerjoin(
        Classification, Classification.id == Article.current_classification_id).where(Article.incident_id == i.id)
        .order_by(Article.published_at.desc().nullslast())).all()
    hist = db.scalars(select(IncidentHistory).where(IncidentHistory.incident_id == i.id)
                      .order_by(IncidentHistory.changed_at.desc())).all()
    articles = []
    for a, c in rows:
        articles.append({"id": a.id, "title": a.title, "source_name": a.source_name, "source_url": a.source_url,
                         "published_at": iso(a.published_at), "review_status": a.review_status,
                         "severity": c.severity if c else None, "time_status": c.time_status if c else None,
                         "evidence_excerpt": c.evidence_excerpt if c else None,
                         "evidence_verified": c.evidence_verified if c else None,
                         "model_confidence": c.model_confidence if c else None,
                         "classified_by": f"{c.provider}/{c.model}" if c and c.model else (c.provider if c else None),
                         "locality": c.locality if c else None, "road_name": c.road_name if c else None})
    return {"incident": incident_row(i, stale), "articles": articles, "history": [row_dict(h) for h in hist],
            "allowed_transitions": sorted(inc_svc.TRANSITIONS.get(i.status, set()))}


class StatusIn(BaseModel):
    status: str
    note: str | None = Field(default=None, max_length=500)


@router.post("/api/incidents/{incident_id}/status")
def change_status(incident_id: str, body: StatusIn, db: Session = Depends(get_db), actor: str = Depends(actor_from)):
    i = db.get(Incident, incident_id)
    if i is None:
        raise HTTPException(404, "Incident not found")
    try:
        inc_svc.transition(db, i, body.status, actor, body.note)
    except ValueError as e:
        raise HTTPException(409, str(e)) from e
    db.commit()
    return {"id": i.id, "status": i.status}


class MergeIn(BaseModel):
    target_id: str
    confirm: bool = False
    note: str | None = Field(default=None, max_length=500)


@router.post("/api/incidents/{incident_id}/merge")
def merge_incident(incident_id: str, body: MergeIn, db: Session = Depends(get_db), actor: str = Depends(actor_from)):
    """Move all articles of this incident into ``target_id``. Source articles are preserved."""
    if not body.confirm:
        raise HTTPException(400, "Merging requires confirm=true")
    src, dst = db.get(Incident, incident_id), db.get(Incident, body.target_id)
    if src is None or dst is None or src.id == dst.id:
        raise HTTPException(404, "Both incidents must exist and differ")
    moved = 0
    for a in db.scalars(select(Article).where(Article.incident_id == src.id)):
        a.incident_id = dst.id
        moved += 1
    db.flush()
    inc_svc.refresh_incident(db, dst)
    inc_svc.refresh_incident(db, src)
    if src.status != "DISMISSED":
        db.add(IncidentHistory(incident_id=src.id, from_status=src.status, to_status="DISMISSED", actor=actor,
                               note=f"Merged into {dst.id}" + (f": {body.note}" if body.note else "")))
        src.status = "DISMISSED"
    audit.record(db, "incident", src.id, "merged", actor, into=dst.id, articles_moved=moved, note=body.note)
    db.commit()
    return {"merged_into": dst.id, "articles_moved": moved}


class DetachIn(BaseModel):
    article_id: str


@router.post("/api/incidents/{incident_id}/detach")
def detach(incident_id: str, body: DetachIn, db: Session = Depends(get_db), actor: str = Depends(actor_from)):
    a = db.get(Article, body.article_id)
    if a is None or a.incident_id != incident_id:
        raise HTTPException(404, "Article is not linked to this incident")
    inc_svc.detach_article(db, a, actor, "detached by operator")
    audit.record(db, "article", a.id, "detached", actor, incident_id=incident_id)
    db.commit()
    return {"ok": True}


# ----------------------------------------------------------------------------- map
@router.get("/api/map/incidents")
def map_incidents(request: Request, db: Session = Depends(get_db)):
    """GeoJSON of incidents with an approximate position, plus a count of those that cannot be mapped."""
    stale = int(settings_store.get(db, "incidents").get("stale_after_hours", 72))
    f = incident_filters(request)
    include_state = request.query_params.get("include_state_level") in ("1", "true")
    base = apply_incident_filters(select(Incident), f, stale)
    total = db.scalar(apply_incident_filters(select(func.count(Incident.id)), f, stale)) or 0
    allowed = ("CITY", "LOCALITY", "MANUAL", "STATE") if include_state else ("CITY", "LOCALITY", "MANUAL")
    mapped = db.scalars(base.where(Incident.latitude.is_not(None), Incident.geo_precision.in_(allowed))
                        .order_by(Incident.last_reported_at.desc()).limit(5000)).all()
    feats = []
    for i in mapped:
        r = incident_row(i, stale)
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [i.longitude, i.latitude]},
                      "properties": {k: r[k] for k in ("id", "title", "category", "severity", "status", "is_stale",
                                                        "city", "state", "road_name", "highway_number", "geo_precision",
                                                        "location_note", "last_reported_at", "first_reported_at",
                                                        "article_count", "has_conflict", "time_status")}})
    return {"type": "FeatureCollection", "features": feats,
            "meta": {"total_matching": total, "mapped": len(feats), "unmapped": total - len(feats),
                     "note": "Points are approximate centroids of the reported locality/city, not exact incident positions."}}
