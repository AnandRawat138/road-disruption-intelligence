from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.models.event import Event

router = APIRouter()

@router.get("/")
def get_events(db: Session = Depends(get_db)):
    # Fetch events and manually attach their earliest evidence source
    from app.models.evidence import Evidence
    from app.models.article import Article
    events = db.query(Event).order_by(Event.created_at.desc()).limit(100).all()
    
    results = []
    for e in events:
        evidence = db.query(Evidence).filter(Evidence.event_id == e.id).first()
        article = db.query(Article).filter(Article.id == evidence.article_id).first() if evidence else None
        
        event_dict = {
            "id": e.id,
            "event_type": e.event_type,
            "impact_type": e.impact_type,
            "event_name": e.event_name,
            "description": e.description,
            "city": e.city,
            "state": e.state,
            "start_time": e.start_time,
            "end_time": e.end_time,
            "severity": e.severity,
            "certainty": e.certainty,
            "status": e.status,
            "source_name": article.source_name if article else (evidence.source_name if evidence else "Local News / Official Update"),
            "source_url": article.source_url if article else "#"
        }
        results.append(event_dict)
    return results

@router.get("/{event_id}")
def get_event(event_id: str, db: Session = Depends(get_db)):
    return db.query(Event).filter(Event.id == event_id).first()
