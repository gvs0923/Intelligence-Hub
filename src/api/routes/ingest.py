from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.db.models import DataSource, IngestionJob
from src.db.session import SessionLocal
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


@router.post("", status_code=202)
def trigger_ingest(req: IngestRequest, db=Depends(get_db)):
    data_source = DataSource(
        name=req.name, source_type=req.source_type, location=req.location
    )
    db.add(data_source)
    db.flush()

    job = IngestionJob(data_source_id=data_source.id)
    db.add(job)
    db.flush()

    if req.source_type not in {"markdown", "code", "git"}:
        raise HTTPException(400, f"Unknown source_type: {req.source_type}")

    db.commit()
    run_ingestion.delay(job.id)
    return {"job_id": job.id, "data_source_id": data_source.id, "status": "queued"}


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