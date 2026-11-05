import argparse
from pathlib import Path

from sqlalchemy import select

from src.db.models import DataSource, IngestionJob
from src.db.session import SessionLocal, init_db
from src.ingestion.pipeline import IngestionPipeline
from src.ingestion.registry import get_chunker, get_ingester


def ingest_source(db, name: str, source_type: str, location: str):
    source = db.scalar(
        select(DataSource).where(
            DataSource.source_type == source_type,
            DataSource.location == location,
        )
    )
    if source is None:
        source = DataSource(
            name=name,
            source_type=source_type,
            location=location,
        )
        db.add(source)
        db.flush()

    job = IngestionJob(data_source_id=source.id)
    db.add(job)
    db.flush()


    pipeline = IngestionPipeline(
        get_ingester(source_type),
        get_chunker(source_type),
        db,
    )
    pipeline.run(job)

    if job.status != "done":
        raise RuntimeError(f"Ingestion failed: {job.error_message}")

    print(f"{name}: source_id={source.id}, job_id={job.id}, status={job.status}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--docs", required=True, type=Path)
    parser.add_argument("--incidents", required=True, type=Path)
    parser.add_argument("--repo", required=True)
    args = parser.parse_args()

    docs = args.docs.expanduser().resolve()
    incidents = args.incidents.expanduser().resolve()

    if not docs.is_dir():
        parser.error("--docs must point to a directory")
    if not incidents.is_file():
        parser.error("--incidents must point to a JSON or CSV file")

    init_db()
    with SessionLocal() as db:
        ingest_source(db, "demo-docs", "markdown", str(docs))
        ingest_source(db, "demo-incidents", "incident", str(incidents))
        ingest_source(db, "demo-repository", "git", args.repo)


if __name__ == "__main__":
    main()