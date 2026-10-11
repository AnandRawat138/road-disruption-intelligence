from sqlalchemy import Column, String, Float
# Removed postgres UUID, using standard string/uuid handling for SQLite compatibility
from sqlalchemy.types import String as StringType
import uuid
from app.db.database import Base

def generate_uuid():
    return str(uuid.uuid4())

class Road(Base):
    __tablename__ = "roads"

    id = Column(StringType, primary_key=True, default=generate_uuid)
    osm_id = Column(String, unique=True, index=True)
    name = Column(String, index=True)
    highway_number = Column(String, nullable=True)
    highway_type = Column(String) 
    city = Column(String, index=True)
    state = Column(String, index=True)
    
    # Store simplified center coords instead of PostGIS LineString for Lite version
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    geometry_json = Column(String, nullable=True) # Holds stringified GeoJSON coordinates
    
    matching_confidence = Column(Float, default=1.0)
