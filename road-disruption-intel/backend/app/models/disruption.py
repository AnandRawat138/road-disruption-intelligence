from sqlalchemy import Column, String, Float, ForeignKey, DateTime
import uuid
from datetime import datetime
from app.db.database import Base

def generate_uuid():
    return str(uuid.uuid4())

class Disruption(Base):
    __tablename__ = "disruptions"

    id = Column(String, primary_key=True, default=generate_uuid)
    event_id = Column(String, ForeignKey('events.id', ondelete='CASCADE'), index=True)
    road_id = Column(String, ForeignKey('roads.id', ondelete='CASCADE'), index=True)
    
    impact_type = Column(String)
    severity = Column(Float)
    confidence = Column(Float)
    
    start_time = Column(DateTime)
    end_time = Column(DateTime)
    status = Column(String, default="UPCOMING")
    
    created_at = Column(DateTime, default=datetime.utcnow)
