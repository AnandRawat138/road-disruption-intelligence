from sqlalchemy import Column, String, Text, DateTime, Float, JSON
import uuid
from datetime import datetime
from app.db.database import Base

def generate_uuid():
    return str(uuid.uuid4())

class Event(Base):
    __tablename__ = "events"

    id = Column(String, primary_key=True, default=generate_uuid)
    event_type = Column(String, index=True) 
    impact_type = Column(String) 
    event_name = Column(String)
    description = Column(Text)
    city = Column(String, index=True)
    state = Column(String, index=True)
    start_time = Column(DateTime, nullable=True)
    end_time = Column(DateTime, nullable=True)
    
    original_temporal_expression = Column(String, nullable=True)
    temporal_confidence = Column(Float, default=1.0)
    
    severity = Column(Float, default=0.0)
    certainty = Column(Float, default=0.0)
    road_risk_score = Column(Float, default=0.0)
    
    status = Column(String, default="UPCOMING")
    
    extracted_locations = Column(JSON, default=list)
    extracted_roads = Column(JSON, default=list)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
