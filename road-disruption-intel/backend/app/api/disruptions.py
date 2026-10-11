from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.models.disruption import Disruption
from app.models.road import Road
from app.models.event import Event
import json

router = APIRouter()

@router.get("/active")
def get_active_disruptions(db: Session = Depends(get_db)):
    from sqlalchemy import or_
    disruptions = db.query(Disruption, Road, Event).join(Road).join(Event).filter(
        or_(Disruption.status == "ACTIVE", Disruption.status == "OPEN_ENDED")
    ).all()
    
    results = []
    for d, r, e in disruptions:
        results.append({
            "id": d.id,
            "event_id": e.id,
            "road_name": r.name,
            "highway_type": r.highway_type,
            "highway_number": r.highway_number,
            "impact_type": d.impact_type,
            "severity": d.severity,
            "confidence": d.confidence,
            "road_risk_score": getattr(e, 'road_risk_score', 0.0),
            "matching_confidence": getattr(r, 'matching_confidence', 1.0),
            "event_name": e.event_name,
            "event_type": e.event_type,
            "description": e.description,
            "status": d.status,
            "start_time": d.start_time.isoformat() if d.start_time else None,
            "end_time": d.end_time.isoformat() if d.end_time else None,
            "temporal_expression": getattr(e, 'original_temporal_expression', ''),
            "city": r.city,
            "state": r.state,
            "geometry": json.loads(r.geometry_json) if r.geometry_json else {
                "type": "LineString",
                "coordinates": [
                    [r.longitude - 0.05, r.latitude - 0.05],
                    [r.longitude, r.latitude],
                    [r.longitude + 0.05, r.latitude + 0.05]
                ]
            }
        })
    return results
