from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.db.database import get_db
from app.services.routing.router import RoutingService

router = APIRouter()
routing_service = RoutingService()

from typing import Optional
from datetime import datetime

class RouteRequest(BaseModel):
    origin: str
    destination: str
    departure_time: Optional[datetime] = None

@router.post("")
@router.post("/")
def calculate_route(req: RouteRequest, db: Session = Depends(get_db)):
    result = routing_service.calculate_route(db, req.origin, req.destination, req.departure_time)
    return result
