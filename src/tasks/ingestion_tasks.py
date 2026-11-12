from src.db.models import IngestionJob
from src.db.session import SessionLocal
from src.indexing.bm25 import BM25Index
from src.indexing.embedders import get_embedder
from src.indexing.indexer import Indexer
from src.indexing.vector_store import VectorStore
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
            indexer=Indexer(get_embedder(), VectorStore(), BM25Index()),
            ingester=get_ingester(data_source.source_type),
            chunker=get_chunker(data_source.source_type),
            session=db,
        )
        pipeline.run(job)
        return job.status
    finally:
        db.close()