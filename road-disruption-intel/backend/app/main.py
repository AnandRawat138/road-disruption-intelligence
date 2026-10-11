import asyncio
import threading
from fastapi import FastAPI
from app.api import articles, events, roads, disruptions, routes, analytics
from app.db.database import engine, Base
from app.workers.ingestion import run_ingestion
from app.workers.processing import run_processing
import time

app = FastAPI(title="Road Disruption Intelligence API")

# Initialize DB 
from app.models.location import Location
from app.models.config import AppConfig
Base.metadata.create_all(bind=engine)

app.include_router(articles.router, prefix="/api/articles", tags=["articles"])
app.include_router(events.router, prefix="/api/events", tags=["events"])
app.include_router(roads.router, prefix="/api/roads", tags=["roads"])
app.include_router(disruptions.router, prefix="/api/disruptions", tags=["disruptions"])
app.include_router(routes.router, prefix="/api/routes", tags=["routes"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["analytics"])

from app.api import admin
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])

def background_task_loop():
    while True:
        try:
            # Enable automatic fetching and processing
            run_ingestion()
            run_processing()
        except Exception as e:
            print(f"Background loop error: {e}")
        time.sleep(60) # Run every minute for the prototype

@app.on_event("startup")
def startup_event():
    # Start the background tasks in a separate thread so it doesn't block FastAPI
    thread = threading.Thread(target=background_task_loop, daemon=True)
    thread.start()

@app.get("/")
def read_root():
    return {"status": "ok", "message": "Road Disruption System (Lite) is running"}
