import json

from sqlalchemy import func, select

from src.db.models import Chunk as ChunkRow
from src.db.models import DataSource, IngestionJob
from src.db.models import Document as DocumentRow
from src.ingestion.chunkers.incident import IncidentChunker
from src.ingestion.incident import IncidentIngester
from src.ingestion.pipeline import IngestionPipeline


def test_incident_pipeline_dedup_and_change(db_session, tmp_path):
    path = tmp_path / "incidents.json"
    record = {
        "id": "INC-001",
        "title": "Login failure",
        "description": "Users could not sign in.",
        "root_cause": "Connection pool exhausted.",
    }
    path.write_text(json.dumps([record]), encoding="utf-8")

    source = DataSource(
        name="incidents",
        source_type="incident",
        location=str(path),
    )
    db_session.add(source)
    db_session.flush()

    pipeline = IngestionPipeline(
        IncidentIngester(),
        IncidentChunker(),
        db_session,
    )

    def run_job():
        job = IngestionJob(data_source_id=source.id)
        db_session.add(job)
        db_session.flush()
        pipeline.run(job)
        assert job.status == "done"

    def chunk_count():
        return db_session.scalar(
            select(func.count()).select_from(ChunkRow)
        )

    run_job()
    assert chunk_count() == 2
    document = db_session.scalar(select(DocumentRow))
    original_hash = document.content_hash

    run_job()
    assert chunk_count() == 2
    assert document.content_hash == original_hash

    record["resolution"] = "Increased pool capacity."
    path.write_text(json.dumps([record]), encoding="utf-8")

    run_job()
    assert chunk_count() == 3
    assert document.content_hash != original_hash
    assert db_session.scalar(
        select(func.count()).select_from(DocumentRow)
    ) == 1

def test_chunking_failure_rolls_back_partial_writes(db_session, tmp_path):
    path = tmp_path / "incidents.json"
    path.write_text(
        json.dumps(
            [
                {
                    "id": "INC-001",
                    "title": "First incident",
                    "description": "First description.",
                },
                {
                    "id": "INC-002",
                    "title": "Second incident",
                    "description": "Second description.",
                },
            ]
        ),
        encoding="utf-8",
    )

    source = DataSource(
        name="failure-test",
        source_type="incident",
        location=str(path),
    )
    db_session.add(source)
    db_session.flush()

    class FailingChunker(IncidentChunker):
        def chunk(self, document):
            if document.metadata["incident_id"] == "INC-002":
                raise ValueError("Deliberate test failure")
            return super().chunk(document)

    job = IngestionJob(data_source_id=source.id)
    db_session.add(job)
    db_session.flush()

    IngestionPipeline(
        IncidentIngester(),
        FailingChunker(),
        db_session,
    ).run(job)

    assert job.status == "failed"
    assert job.error_message == "Deliberate test failure"
    assert db_session.scalar(
        select(func.count()).select_from(DocumentRow)
    ) == 0
    assert db_session.scalar(
        select(func.count()).select_from(ChunkRow)
    ) == 0