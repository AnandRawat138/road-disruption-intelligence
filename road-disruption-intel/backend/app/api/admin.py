from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.models.config import AppConfig
from pydantic import BaseModel

router = APIRouter()

class ConfigUpdate(BaseModel):
    value: str

@router.get("/")
def get_all_configs(db: Session = Depends(get_db)):
    configs = db.query(AppConfig).all()
    # Mask sensitive keys
    result = []
    for c in configs:
        val = c.config_value
        if c.is_sensitive and val:
            val = "********"
        result.append({
            "key": c.config_key,
            "value": val,
            "type": c.config_type,
            "description": c.description
        })
    return result

@router.post("/{key}")
def update_config(key: str, payload: ConfigUpdate, db: Session = Depends(get_db)):
    config_item = db.query(AppConfig).filter(AppConfig.config_key == key).first()
    if not config_item:
        config_item = AppConfig(config_key=key, config_value=payload.value)
        db.add(config_item)
    else:
        config_item.config_value = payload.value
    db.commit()
    return {"status": "success", "key": key}
