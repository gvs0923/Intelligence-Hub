from sqlalchemy import func, select

from src.db.models import Chunk, IngestionJob
from src.indexing.bm25 import BM25Index
from src.indexing.indexer import Indexer
from src.indexing.vector_store import VectorStore
from src.ingestion.pipeline import IngestionPipeline
from src.ingestion.registry import get_chunker, get_ingester


class DeterministicEmbedder:
    @property
    def dimension(self):
        return 3

    def embed(self, texts):
        return [[float(len(text)), 1.0, 1.0] for text in texts]


def test_ingestion_indexes_and_reingestion_is_idempotent(
    db_session, data_source, tmp_path
):
    (tmp_path / "guide.md").write_text(
        "# Pod eviction\n\n"
        "Kubernetes may evict a pod when the node experiences memory pressure.\n",
        encoding="utf-8",
    )

    store = VectorStore(str(tmp_path / "vectors"))
    bm25_path = str(tmp_path / "bm25.pkl")
    indexer = Indexer(
        DeterministicEmbedder(),
        store,
        BM25Index(bm25_path),
    )
    pipeline = IngestionPipeline(
        get_ingester("markdown"),
        get_chunker("markdown"),
        db_session,
        indexer=indexer,
    )

    def run_job():
        job = IngestionJob(data_source_id=data_source.id)
        db_session.add(job)
        db_session.flush()
        pipeline.run(job)
        assert job.status == "done", job.error_message

    run_job()

    first_count = db_session.scalar(select(func.count()).select_from(Chunk))
    assert first_count > 0
    assert store.count() == first_count

    restored = BM25Index(bm25_path)
    assert restored.load() is True
    assert restored.query("eviction", 5)

    run_job()

    second_count = db_session.scalar(select(func.count()).select_from(Chunk))
    assert second_count == first_count
    assert store.count() == first_count