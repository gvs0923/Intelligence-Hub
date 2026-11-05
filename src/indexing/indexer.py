from src.indexing.base import BaseEmbedder
from src.indexing.bm25 import BM25Index
from src.indexing.vector_store import VectorStore
from src.logging_config import get_logger

log = get_logger(__name__)


class Indexer:
    """Coordinates: embed chunks -> write to Chroma -> rebuild BM25."""

    def __init__(self, embedder: BaseEmbedder, vector_store: VectorStore, bm25: BM25Index):
        self.embedder = embedder
        self.vector_store = vector_store
        self.bm25 = bm25

    def index_chunks(self, vector_ids: list[str], texts: list[str], metadatas: list[dict]) -> None:
        if not vector_ids:
            return
        existing_dim = self.vector_store.dimension
        if existing_dim is not None and existing_dim != self.embedder.dimension:
            raise RuntimeError(
                f"Embedding dim mismatch: index has {existing_dim}, "
                f"embedder produces {self.embedder.dimension}. "
                "Wipe the Chroma collection or use a consistent embedder."
            )
        embeddings = self.embedder.embed(texts)
        self.vector_store.add(vector_ids, embeddings, metadatas)
        if existing_dim is None:
            self.vector_store.set_dimension(self.embedder.dimension)
        log.info("chunks_indexed", count=len(vector_ids), dim=self.embedder.dimension)

    def rebuild_bm25(self, rows: list[tuple[str, str]]) -> None:
        """rows = [(vector_id, text), ...] for ALL chunks in the DB."""
        self.bm25.build([r[0] for r in rows], [r[1] for r in rows])

    def delete_vectors(self, vector_ids: list[str]) -> None:
        self.vector_store.delete(vector_ids)