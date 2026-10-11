from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class EventExtractionSchema(BaseModel):
    event_type: str = Field(description="PROTEST, RALLY, ROAD_SHOW, VIP_MOVEMENT, STRIKE, ACCIDENT, FLOOD, WATERLOGGING, CONSTRUCTION, OTHER")
    impact_type: str = Field(description="FULL_CLOSURE, PARTIAL_CLOSURE, TRAFFIC_DIVERSION, HEAVY_TRAFFIC, POTENTIAL_BLOCKAGE")
    event_name: str
    description: str
    city: Optional[str] = None
    state: Optional[str] = None
    locations: List[str] = Field(default_factory=list)
    roads: List[str] = Field(default_factory=list)
    landmarks: List[str] = Field(default_factory=list)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    temporal_expression: str = Field(description="Original temporal expression from text (e.g., 'tomorrow morning', 'until further notice')")
    severity: float = Field(ge=0.0, le=1.0)
    extraction_confidence: float = Field(ge=0.0, le=1.0)
    evidence_text: List[str] = Field(default_factory=list)
    source_article_id: Optional[str] = None

class EventResponse(BaseModel):
    id: str
    event_type: str
    impact_type: str
    event_name: str
    city: str
    state: str
    severity: float
    certainty: float
    status: str

    class Config:
        orm_mode = True
        from_attributes = True
