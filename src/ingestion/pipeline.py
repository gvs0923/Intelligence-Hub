from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db.models import Chunk as ChunkRow
from src.db.models import Document as DocumentRow
from src.db.models import IngestionJob
from src.ingestion.base import BaseIngester
from src.ingestion.chunkers.base import BaseChunker
from src.ingestion.hashing import content_hash
from src.logging_config import get_logger

log = get_logger(__name__)


class IngestionPipeline:
    """Orchestrates: ingest -> dedup-check -> chunk -> persist."""

    def __init__(self, ingester: BaseIngester, chunker: BaseChunker, session: Session):
        self.ingester = ingester
        self.chunker = chunker
        self.session = session

    def run(self, job: IngestionJob) -> IngestionJob:
        job.status = "running"
        job.started_at = datetime.now(UTC)
        self.session.commit()

        try:
            data_source = job.data_source
            existing = {
                row.path: row
                for row in self.session.scalars(
                    select(DocumentRow).where(DocumentRow.data_source_id == data_source.id)
                )
            }

            documents = self.ingester.ingest(data_source.location)
            stats = {"documents": len(documents), "skipped": 0, "chunks": 0}

            for doc in documents:
                digest = content_hash(doc.content)
                row = existing.get(doc.source_path)
                if row and row.content_hash == digest:
                    stats["skipped"] += 1
                    continue

                if row:  # changed file — replace its chunks
                    self.session.query(ChunkRow).filter_by(document_id=row.id).delete()
                    row.content_hash = digest
                else:
                    row = DocumentRow(
                        data_source_id=data_source.id,
                        path=doc.source_path,
                        content_hash=digest,
                    )
                    self.session.add(row)
                    self.session.flush()  # get row.id before inserting chunks

                chunks = self.chunker.chunk(doc)
                for i, chunk in enumerate(chunks):
                    # vector_id is a placeholder until Phase 3 embeds into Chroma
                    self.session.add(ChunkRow(
                        document_id=row.id,
                        chunk_index=i,
                        vector_id=f"doc{row.id}-chunk{i}",
                    ))
                stats["chunks"] += len(chunks)

            job.status = "done"
            log.info("ingestion_complete", job_id=job.id, **stats)

        except Exception as exc:  # noqa: BLE001 - any failure here must mark the job failed, not crash it
            job.status = "failed"
            job.error_message = str(exc)
            log.error("ingestion_failed", job_id=job.id, error=str(exc))

        job.completed_at = datetime.now(UTC)
        self.session.commit()
        return job