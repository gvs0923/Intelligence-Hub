from src.db.models import Chunk
from src.db.session import SessionLocal
from src.indexing.base import BaseEmbedder
from src.indexing.vector_store import VectorStore
from src.logging_config import get_logger
from src.retrieval.base import RetrievalResult

log = get_logger(__name__)


class DenseRetriever:
    """Embeds the query and asks ChromaDB for the nearest chunk vectors.
    Chroma returns vector_ids + distances; we join back to SQLite for the text."""

    def __init__(self, embedder: BaseEmbedder, vector_store: VectorStore):
        self.embedder = embedder
        self.vector_store = vector_store

    def retrieve(self, query: str, top_k: int, where: dict | None = None) -> list[RetrievalResult]:
        embedding = self.embedder.embed([query])[0]
        resp = self.vector_store.query(embedding, top_k=top_k, where=where)

        vector_ids = resp.get("ids", [[]])[0]
        distances = resp.get("distances", [[]])[0]
        metadatas = resp.get("metadatas", [[]])[0]
        if not vector_ids:
            return []

        # Join back to SQLite for chunk text (Chroma only stores ids + metadata)
        with SessionLocal() as session:
            chunks = {
                c.vector_id: c
                for c in session.query(Chunk).filter(Chunk.vector_id.in_(vector_ids)).all()
            }

        results = []
        for vid, dist, meta in zip(vector_ids, distances, metadatas):
            chunk = chunks.get(vid)
            if chunk is None:
                continue  # vector exists but chunk row deleted — skip stale vectors
            results.append(
                RetrievalResult(
                    content=chunk.text,
                    score=1.0 - dist,  # cosine distance → similarity
                    metadata={**(meta or {}), "vector_id": vid},
                )
            )
        log.info("dense_retrieved", count=len(results))
        return results