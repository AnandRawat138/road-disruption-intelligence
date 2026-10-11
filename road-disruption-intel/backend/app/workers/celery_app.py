import os
from celery import Celery
from app.config import settings

celery_app = Celery(
    "road_disruption_worker",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=['app.workers.ingestion', 'app.workers.processing']
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=True,
)

# Weekly reporting task schedule can be added here
@celery_app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    # Poll news every X minutes
    sender.add_periodic_task(
        settings.NEWS_POLL_INTERVAL_MINUTES * 60.0,
        trigger_news_ingestion.s(),
        name='Ingest news periodically'
    )

@celery_app.task
def trigger_news_ingestion():
    from app.workers.ingestion import ingest_news_task
    ingest_news_task.delay()
