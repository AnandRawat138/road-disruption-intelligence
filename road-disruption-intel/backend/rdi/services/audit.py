"""Append-only audit trail. Never store secrets or personal data here."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from ..db.models import AuditLog


def _jsonable(v):
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    if isinstance(v, dict):
        return {k: _jsonable(x) for k, x in v.items()}
    return v


def record(db: Session, entity_type: str, entity_id: str, action: str, actor: str | None = None,
           **details) -> None:
    db.add(AuditLog(entity_type=entity_type, entity_id=str(entity_id)[:64], action=action[:40],
                    actor=(actor or "system")[:100], details=_jsonable(details)))
