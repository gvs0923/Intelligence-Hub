from celery import Celery

from src.config import get_settings

settings = get_settings()

celery_app = Celery(
    "intelligencehub",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["src.tasks.ingestion_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    task_track_started=True,
)