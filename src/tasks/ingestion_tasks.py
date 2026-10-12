from src.db.models import IngestionJob
from src.db.session import SessionLocal
from src.ingestion.pipeline import IngestionPipeline
from src.ingestion.registry import get_chunker, get_ingester
from src.tasks.celery_app import celery_app


@celery_app.task(name="run_ingestion")
def run_ingestion(job_id: int) -> str:
    db = SessionLocal()
    try:
        job = db.get(IngestionJob, job_id)
        data_source = job.data_source
        pipeline = IngestionPipeline(
            ingester=get_ingester(data_source.source_type),
            chunker=get_chunker(data_source.source_type),
            session=db,
        )
        pipeline.run(job)
        return job.status
    finally:
        db.close()