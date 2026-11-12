from src.db.models import Chunk
from src.db.session import SessionLocal
from src.indexing.bm25 import BM25Index
from src.logging_config import get_logger
from src.retrieval.base import RetrievalResult

log = get_logger(__name__)


class BM25Retriever:
    """Keyword search over the BM25 index. Returns (vector_id, bm25_score)
    pairs, then joins to SQLite for text."""

    def __init__(self, bm25: BM25Index):
        self.bm25 = bm25

    def retrieve(self, query: str, top_k: int) -> list[RetrievalResult]:
        scored = self.bm25.query(query, top_k)  # [(vector_id, score)]
        if not scored:
            return []

        ids = [vid for vid, _ in scored]
        with SessionLocal() as session:
            chunks = {
                c.vector_id: c
                for c in session.query(Chunk).filter(Chunk.vector_id.in_(ids)).all()
            }

        results = [
            RetrievalResult(
                content=chunks[vid].text,
                score=score,
                metadata={"vector_id": vid},
            )
            for vid, score in scored
            if vid in chunks
        ]
        log.info("bm25_retrieved", count=len(results))
        return results