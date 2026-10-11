from sqlalchemy import Column, String, Text, Boolean, Integer, Float, DateTime
import uuid
from datetime import datetime
from app.db.database import Base

def generate_uuid():
    return str(uuid.uuid4())

class AppConfig(Base):
    __tablename__ = "app_config"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    config_key = Column(String, unique=True, index=True)
    config_value = Column(Text, nullable=True)
    config_type = Column(String, default="string") # boolean, float, integer, string, json
    description = Column(Text, nullable=True)
    is_sensitive = Column(Boolean, default=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
