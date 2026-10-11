"""Shared API helpers: actor identification, serialisation, pagination, errors."""
from __future__ import annotations

import re
from datetime import date, datetime, time
from typing import Any

from fastapi import Header, HTTPException, Query

from ..services.text import parse_timestamp


def actor_from(x_operator: str | None = Header(default=None)) -> str:
    """Operator display name sent by the UI. This is attribution only, not authentication."""
    if not x_operator:
        return "operator"
    clean = re.sub(r"[^\w .@-]", "", x_operator)[:60].strip()
    return clean or "operator"


def iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.replace(microsecond=0).isoformat() + "Z"


def to_jsonable(v: Any) -> Any:
    if isinstance(v, datetime):
        return iso(v)
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, dict):
        return {k: to_jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [to_jsonable(x) for x in v]
    return v


def row_dict(obj, exclude: set[str] | None = None) -> dict:
    exclude = exclude or set()
    return {c: to_jsonable(getattr(obj, c)) for c in obj.__table__.columns.keys() if c not in exclude}


def parse_date_param(value: str | None, end_of_day: bool = False) -> datetime | None:
    if not value:
        return None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        d = date.fromisoformat(value)
        return datetime.combine(d, time.max if end_of_day else time.min)
    dt = parse_timestamp(value)
    if dt is None:
        raise HTTPException(status_code=422, detail=f"Invalid date: {value}")
    return dt


class Page:
    def __init__(self, page: int = Query(1, ge=1, le=100000), page_size: int = Query(25, ge=1, le=200)):
        self.page = page
        self.page_size = page_size

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def page_envelope(items: list, total: int, page: Page) -> dict:
    return {"items": items, "total": total, "page": page.page, "page_size": page.page_size,
            "pages": (total + page.page_size - 1) // page.page_size if page.page_size else 0}


def split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()][:50]
