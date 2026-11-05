import chromadb

from src.config import get_settings
from src.logging_config import get_logger

log = get_logger(__name__)

_COLLECTION = "chunks"


class VectorStore:
    """Thin wrapper over ChromaDB. Chroma stores vectors + metadata;
    SQLite stays the source of truth for chunk text (joined via vector_id)."""

    def __init__(self, persist_dir: str | None = None):
        settings = get_settings()
        path = persist_dir or settings.chroma_persist_dir
        self._client = chromadb.PersistentClient(path=path)
        self._collection = self._client.get_or_create_collection(
            name=_COLLECTION,
            metadata={"hnsw:space": "cosine"},  # cosine similarity for text embeddings
        )

    @property
    def dimension(self) -> int | None:
        return self._collection.metadata.get("embedding_dim")

    def set_dimension(self, dim: int) -> None:
        metadata = {
            key: value
            for key, value in (self._collection.metadata or {}).items()
            if key != "hnsw:space"
        }
        self._collection.modify(metadata={**metadata, "embedding_dim": dim})

    def add(self, ids: list[str], embeddings: list[list[float]], metadatas: list[dict]) -> None:
        self._collection.upsert(
            ids=ids,
            embeddings=embeddings,
            metadatas=[metadata or None for metadata in metadatas],
        )

    def delete(self, ids: list[str]) -> None:
        if ids:
            self._collection.delete(ids=ids)

    def query(self, embedding: list[float], top_k: int, where: dict | None = None) -> dict:
        return self._collection.query(
            query_embeddings=[embedding], n_results=top_k, where=where
        )

    def count(self) -> int:
        return self._collection.count()