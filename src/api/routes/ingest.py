from fastapi import APIRouter, Depends, HTTPException
from kombu.exceptions import OperationalError
from pydantic import BaseModel

from src.db.models import DataSource, IngestionJob
from src.db.session import SessionLocal
from src.ingestion.registry import INGESTERS
from src.tasks.ingestion_tasks import run_ingestion

router = APIRouter(prefix="/ingest", tags=["ingestion"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class IngestRequest(BaseModel):
    name: str
    source_type: str          # "git" | "markdown" | "code"
    location: str             # repo URL or local directory path

def enqueue_ingestion(data_source: DataSource, db):
    job = IngestionJob(data_source_id=data_source.id)
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        run_ingestion.delay(job.id)
    except OperationalError as exc:
        job.status = "failed"
        job.error_message = "Could not publish ingestion task"
        db.commit()
        raise HTTPException(
            status_code=503,
            detail="Ingestion queue unavailable; retry later",
        ) from exc

    return {
        "job_id": job.id,
        "data_source_id": data_source.id,
        "status": "queued",
    }

@router.post("", status_code=202)
def trigger_ingest(req: IngestRequest, db=Depends(get_db)):
    if req.source_type not in INGESTERS:
        raise HTTPException(400, f"Unknown source_type: {req.source_type}")

    data_source = DataSource(
        name=req.name,
        source_type=req.source_type,
        location=req.location,
    )
    db.add(data_source)
    db.flush()

    return enqueue_ingestion(data_source, db)

@router.get("/{job_id}")
def job_status(job_id: int, db=Depends(get_db)):
    job = db.get(IngestionJob, job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    return {
        "id": job.id,
        "status": job.status,
        "error": job.error_message,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
    }

@router.post("/sources/{source_id}/refresh", status_code=202)
def refresh_source(source_id: int, db=Depends(get_db)):
    data_source = db.get(DataSource, source_id)
    if data_source is None:
        raise HTTPException(404, "Data source not found")

    if data_source.source_type not in INGESTERS:
        raise HTTPException(
            400,
            f"Unknown source_type: {data_source.source_type}",
        )

    return enqueue_ingestion(data_source, db)
