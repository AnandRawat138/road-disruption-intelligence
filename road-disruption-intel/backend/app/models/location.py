from sqlalchemy import Column, String, Float, ForeignKey
from sqlalchemy.types import String as StringType
import uuid
from app.db.database import Base

def generate_uuid():
    return str(uuid.uuid4())

class Location(Base):
    __tablename__ = "locations"

    id = Column(StringType, primary_key=True, default=generate_uuid)
    event_id = Column(String, ForeignKey('events.id', ondelete='CASCADE'), index=True)
    
    location_name = Column(String, index=True)
    location_type = Column(String, default="UNKNOWN") # e.g. LANDMARK, NEIGHBORHOOD, INTERSECTION
    city = Column(String, index=True)
    state = Column(String, index=True)
    
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    
    location_confidence = Column(Float, default=1.0)
    original_text = Column(String, nullable=True)
