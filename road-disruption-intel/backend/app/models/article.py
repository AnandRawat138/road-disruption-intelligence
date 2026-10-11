from sqlalchemy import Column, String, Text, DateTime, Float
import uuid
from datetime import datetime
from app.db.database import Base

def generate_uuid():
    return str(uuid.uuid4())

class Article(Base):
    __tablename__ = "articles"

    id = Column(String, primary_key=True, default=generate_uuid)
    title = Column(String, index=True)
    description = Column(Text)
    content = Column(Text)
    source_name = Column(String, index=True)
    source_url = Column(String, unique=True)
    published_at = Column(DateTime)
    collected_at = Column(DateTime, default=datetime.utcnow)
    language = Column(String, default="en")
    city = Column(String, index=True)
    content_hash = Column(String, unique=True, index=True)
    relevance_score = Column(Float, nullable=True)
    relevance_reason = Column(Text, nullable=True)
    status = Column(String, default="PENDING")
