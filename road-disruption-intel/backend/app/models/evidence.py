from sqlalchemy import Column, String, Float, ForeignKey, Boolean
import uuid
from app.db.database import Base

def generate_uuid():
    return str(uuid.uuid4())

class Evidence(Base):
    __tablename__ = "evidence"

    id = Column(String, primary_key=True, default=generate_uuid)
    event_id = Column(String, ForeignKey('events.id', ondelete='CASCADE'), index=True)
    article_id = Column(String, ForeignKey('articles.id', ondelete='CASCADE'), index=True)
    
    source_name = Column(String)
    source_type = Column(String, default="NEWS")
    source_reliability = Column(Float, default=0.5)
    
    support_score = Column(Float, default=1.0)
    contradiction_score = Column(Float, default=0.0)
    
    semantic_similarity = Column(Float, default=1.0)
    temporal_agreement = Column(Float, default=1.0)
    geographic_agreement = Column(Float, default=1.0)
    
    evidence_text = Column(String)
