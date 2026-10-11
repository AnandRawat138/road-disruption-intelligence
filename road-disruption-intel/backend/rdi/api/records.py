"""Records (articles + current classification) API."""
from __future__ import annotations

import csv
import io
import json
import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from ..db.models import Article, ArticleSighting, AuditLog, Classification, Incident, utcnow
from ..db.session import get_db
from ..services import audit, incidents
from ..services.classification.classifier import EDITABLE_FIELDS, human_correction, is_headline_only
from .common import Page, actor_from, iso, page_envelope, parse_date_param, row_dict, split_csv

router = APIRouter(prefix="/api/records", tags=["records"])

SEVERITY_ORDER = case({"CRITICAL": 4, "HIGH": 3, "MODERATE": 2, "LOW": 1}, value=Classification.severity, else_=0)
SORTS = {
    "published_at": Article.published_at, "ingested_at": Article.ingested_at, "title": Article.title,
    "source": Article.source_name, "severity": SEVERITY_ORDER, "category": Classification.category,
    "event_start": Classification.event_start, "updated_at": Article.updated_at, "city": Classification.city,
}
LIST_PARAMS = ("category", "severity", "relevance", "classification_status", "review_status", "prefilter",
               "connector", "time_status", "geo_precision", "source")


def filters_from_request(request: Request) -> dict:
    qp = request.query_params
    f: dict = {}
    for key in ("q", "state", "city", "highway", "date_from", "date_to", "incident_id", "has_coords", "needs_review",
                "include_near_duplicates", "event_from", "event_to"):
        if qp.get(key) not in (None, ""):
            f[key] = qp.get(key)
    for key in LIST_PARAMS:
        vals = split_csv(qp.get(key))
        if vals:
            f[key] = vals
    return f


def _truthy(v) -> bool:
    return str(v).lower() in ("1", "true", "yes")


def apply_record_filters(q, f: dict):
    q = q.outerjoin(Classification, Classification.id == Article.current_classification_id)
    conds = []
    if f.get("q"):
        term = str(f["q"]).strip()[:200]
        like = f"%{term}%"
        ors = [Article.title.ilike(like), Article.summary_text.ilike(like), Classification.road_name.ilike(like),
               Classification.city.ilike(like), Classification.locality.ilike(like), Classification.state.ilike(like),
               Article.source_name.ilike(like), Classification.highway_number.ilike(like)]
        m = re.fullmatch(r"(?i)\s*(nh|sh)\s*[-–]?\s*(\d{1,4}[a-z]?)\s*", term)
        if m:
            hw = f"{m.group(1).upper()}-{m.group(2).upper()}"
            ors.append(Classification.highway_number == hw)
            ors.append(Article.title.ilike(f"%{m.group(1)} {m.group(2)}%"))
            ors.append(Article.title.ilike(f"%{m.group(1)}-{m.group(2)}%"))
        conds.append(or_(*ors))
    mapping = {"category": Classification.category, "severity": Classification.severity,
               "relevance": Classification.relevance, "classification_status": Article.classification_status,
               "review_status": Article.review_status, "prefilter": Article.prefilter_label,
               "connector": Article.connector, "time_status": Classification.time_status,
               "geo_precision": Classification.geo_precision, "source": Article.source_name}
    for key, col in mapping.items():
        if f.get(key):
            conds.append(col.in_(f[key]))
    if f.get("state"):
        conds.append(func.lower(Classification.state) == str(f["state"]).lower())
    if f.get("city"):
        conds.append(func.lower(Classification.city) == str(f["city"]).lower())
    if f.get("highway"):
        conds.append(Classification.highway_number == str(f["highway"]).upper())
    if f.get("date_from"):
        conds.append(Article.published_at >= parse_date_param(f["date_from"]))
    if f.get("date_to"):
        conds.append(Article.published_at <= parse_date_param(f["date_to"], end_of_day=True))
    if f.get("event_from"):
        conds.append(Classification.event_start >= parse_date_param(f["event_from"]))
    if f.get("event_to"):
        conds.append(Classification.event_start <= parse_date_param(f["event_to"], end_of_day=True))
    if f.get("incident_id"):
        conds.append(Article.incident_id == f["incident_id"])
    if f.get("has_coords") not in (None, ""):
        conds.append(Classification.latitude.is_not(None) if _truthy(f["has_coords"]) else Classification.latitude.is_(None))
    if f.get("needs_review") not in (None, ""):
        conds.append(Classification.needs_review.is_(_truthy(f["needs_review"])))
    if not _truthy(f.get("include_near_duplicates", "false")):
        conds.append(Article.near_duplicate_of.is_(None))
    if conds:
        q = q.where(and_(*conds))
    return q


def record_row(a: Article, c: Classification | None) -> dict:
    return {
        "id": a.id, "title": a.title, "source_name": a.source_name, "source_url": a.source_url,
        "connector": a.connector, "published_at": iso(a.published_at), "ingested_at": iso(a.ingested_at),
        "updated_at": iso(max([d for d in (a.updated_at, c.created_at if c else None) if d] or [a.ingested_at])),
        "prefilter_label": a.prefilter_label, "classification_status": a.classification_status,
        "review_status": a.review_status, "incident_id": a.incident_id,
        "relevance": c.relevance if c else None, "category": c.category if c else None,
        "severity": c.severity if c else None, "state": c.state if c else None, "city": c.city if c else None,
        "locality": c.locality if c else None, "road_name": c.road_name if c else None,
        "highway_number": c.highway_number if c else None, "event_start": iso(c.event_start) if c else None,
        "time_status": c.time_status if c else None, "model_confidence": c.model_confidence if c else None,
        "needs_review": c.needs_review if c else False, "geo_status": c.geo_status if c else None,
        "geo_precision": c.geo_precision if c else None, "latitude": c.latitude if c else None,
        "longitude": c.longitude if c else None, "summary": c.summary if c else None,
        "classified_by": (f"{c.provider}/{c.model}" if c and c.model else (c.provider if c else None)),
        "classified_at": iso(c.created_at) if c else None, "origin": c.origin if c else None,
    }


@router.get("")
def list_records(request: Request, page: Page = Depends(), sort: str = "published_at", order: str = "desc",
                 db: Session = Depends(get_db)):
    f = filters_from_request(request)
    base = apply_record_filters(select(Article, Classification), f)
    total = db.scalar(apply_record_filters(select(func.count(Article.id)), f))
    col = SORTS.get(sort, Article.published_at)
    ordering = col.asc().nullslast() if order == "asc" else col.desc().nullslast()
    rows = db.execute(base.order_by(ordering, Article.id).offset(page.offset).limit(page.page_size)).all()
    return page_envelope([record_row(a, c) for a, c in rows], total or 0, page)


@router.get("/facets")
def facets(db: Session = Depends(get_db)):
    cur = Classification.is_current.is_(True)
    def top(col, where=None, n=200):
        q = select(col, func.count()).where(col.is_not(None))
        if where is not None:
            q = q.where(where)
        return [{"value": v, "count": c} for v, c in db.execute(q.group_by(col).order_by(func.count().desc()).limit(n))]
    return {
        "sources": top(Article.source_name, n=300),
        "connectors": top(Article.connector),
        "states": top(Classification.state, cur),
        "cities": top(Classification.city, cur),
        "highways": top(Classification.highway_number, cur),
    }


@router.get("/export")
def export_records(request: Request, format: str = "csv", sort: str = "published_at", db: Session = Depends(get_db)):
    if format not in ("csv", "json"):
        raise HTTPException(422, "format must be csv or json")
    f = filters_from_request(request)
    limit = 50000
    q = apply_record_filters(select(Article, Classification), f).order_by(
        SORTS.get(sort, Article.published_at).desc().nullslast(), Article.id).limit(limit)
    generated = iso(utcnow())
    columns = ["id", "title", "source_name", "source_url", "published_at", "ingested_at", "relevance", "category",
               "severity", "time_status", "state", "city", "locality", "road_name", "highway_number", "event_start",
               "latitude", "longitude", "geo_precision", "geo_status", "model_confidence", "needs_review",
               "classification_status", "review_status", "incident_id", "classified_by", "classified_at", "origin",
               "summary"]
    extra = ["evidence_excerpt", "advisory_action", "validation_status", "prefilter_label"]
    stamp = utcnow().strftime("%Y%m%d_%H%M")

    def rows():
        for a, c in db.execute(q).yield_per(500):
            r = record_row(a, c)
            r.update({"evidence_excerpt": c.evidence_excerpt if c else None,
                      "advisory_action": c.advisory_action if c else None,
                      "validation_status": c.validation_status if c else None})
            yield r

    if format == "csv":
        def gen():
            buf = io.StringIO()
            w = csv.writer(buf)
            desc = "; ".join(f"{k}={'|'.join(v) if isinstance(v, list) else v}" for k, v in f.items()) or "none"
            desc = re.sub(r'[",\r\n]', " ", desc)
            w.writerow(columns + extra)
            yield ("\ufeff# Road Disruption Intelligence export generated " + generated + " UTC; filters: " + desc
                   + "; coordinates are approximate centroids unless geo_precision=MANUAL\r\n" + buf.getvalue())
            for r in rows():
                buf.seek(0)
                buf.truncate()
                w.writerow([("" if r.get(k) is None else r.get(k)) for k in columns + extra])
                yield buf.getvalue()
        return StreamingResponse(gen(), media_type="text/csv; charset=utf-8",
                                 headers={"Content-Disposition": f'attachment; filename="rdi_records_{stamp}.csv"'})

    def gen_json():
        yield json.dumps({"generated_at": generated, "filters": f, "row_limit": limit,
                          "notes": "Coordinates are approximate centroids unless geo_precision is MANUAL. "
                                   "Model output is advisory; check review_status."})[:-1] + ', "records": ['
        first = True
        for r in rows():
            yield ("" if first else ",") + json.dumps(r, ensure_ascii=False)
            first = False
        yield "]}"
    return StreamingResponse(gen_json(), media_type="application/json",
                             headers={"Content-Disposition": f'attachment; filename="rdi_records_{stamp}.json"'})


@router.get("/{article_id}")
def get_record(article_id: str, db: Session = Depends(get_db)):
    a = db.get(Article, article_id)
    if a is None:
        raise HTTPException(404, "Record not found")
    current = db.get(Classification, a.current_classification_id) if a.current_classification_id else None
    history = db.scalars(select(Classification).where(Classification.article_id == a.id)
                         .order_by(Classification.version.desc())).all()
    sightings = db.scalars(select(ArticleSighting).where(ArticleSighting.article_id == a.id)
                           .order_by(ArticleSighting.seen_at).limit(100)).all()
    inc = db.get(Incident, a.incident_id) if a.incident_id else None
    dupes = db.scalars(select(Article).where(Article.near_duplicate_of == a.id).limit(20)).all()
    events = db.scalars(select(AuditLog).where(AuditLog.entity_type == "article", AuditLog.entity_id == a.id)
                        .order_by(AuditLog.at.desc()).limit(50)).all()
    return {
        "article": {**row_dict(a), "headline_only": is_headline_only(a)},
        "classification": row_dict(current) if current else None,
        "classification_history": [row_dict(c, exclude={"raw_output"}) | {"has_raw_output": bool(c.raw_output)}
                                   for c in history],
        "sightings": [row_dict(s) for s in sightings],
        "incident": row_dict(inc) if inc else None,
        "near_duplicates": [{"id": d.id, "title": d.title, "source_url": d.source_url} for d in dupes],
        "audit": [row_dict(e) for e in events],
        "editable_fields": sorted(EDITABLE_FIELDS),
    }


@router.get("/{article_id}/classifications/{cls_id}/raw")
def get_raw_output(article_id: str, cls_id: str, db: Session = Depends(get_db)):
    c = db.get(Classification, cls_id)
    if c is None or c.article_id != article_id:
        raise HTTPException(404, "Classification not found")
    return {"id": c.id, "raw_output": c.raw_output, "error": c.error}


class CorrectionIn(BaseModel):
    changes: dict = Field(default_factory=dict)
    note: str | None = Field(default=None, max_length=500)


@router.patch("/{article_id}/classification")
def correct_classification(article_id: str, body: CorrectionIn, db: Session = Depends(get_db),
                           actor: str = Depends(actor_from)):
    a = db.get(Article, article_id)
    if a is None:
        raise HTTPException(404, "Record not found")
    if not body.changes:
        raise HTTPException(422, "No changes supplied")
    try:
        cls = human_correction(db, a, body.changes, actor, body.note)
    except ValueError as e:
        db.rollback()
        raise HTTPException(422, str(e)) from e
    db.commit()
    return {"classification": row_dict(cls), "incident_id": a.incident_id}


class ReviewIn(BaseModel):
    decision: str = Field(pattern="^(APPROVED|REJECTED|PENDING_REVIEW)$")
    note: str | None = Field(default=None, max_length=500)


def _review(db: Session, a: Article, decision: str, note: str | None, actor: str) -> None:
    if decision in ("APPROVED", "REJECTED") and not a.current_classification_id:
        raise HTTPException(409, f"Record {a.id} has no classification to review")
    old = a.review_status
    a.review_status = decision
    a.updated_at = utcnow()
    if a.current_classification_id and decision != "PENDING_REVIEW":
        c = db.get(Classification, a.current_classification_id)
        c.needs_review = False
    audit.record(db, "article", a.id, "review", actor, old=old, new=decision, note=note)
    if decision in ("APPROVED", "REJECTED"):
        incidents.on_article_review(db, a, decision, actor)


@router.post("/{article_id}/review")
def review_record(article_id: str, body: ReviewIn, db: Session = Depends(get_db), actor: str = Depends(actor_from)):
    a = db.get(Article, article_id)
    if a is None:
        raise HTTPException(404, "Record not found")
    _review(db, a, body.decision, body.note, actor)
    db.commit()
    return {"id": a.id, "review_status": a.review_status, "incident_id": a.incident_id}


class BulkReviewIn(ReviewIn):
    ids: list[str] = Field(min_length=1, max_length=500)


@router.post("/bulk-review")
def bulk_review(body: BulkReviewIn, db: Session = Depends(get_db), actor: str = Depends(actor_from)):
    done, skipped = 0, []
    for aid in body.ids:
        a = db.get(Article, aid)
        if a is None or (body.decision != "PENDING_REVIEW" and not a.current_classification_id):
            skipped.append(aid)
            continue
        _review(db, a, body.decision, body.note, actor)
        done += 1
    db.commit()
    return {"updated": done, "skipped": skipped}
