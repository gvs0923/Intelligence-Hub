import pickle
from pathlib import Path

from rank_bm25 import BM25Okapi

from src.config import get_settings
from src.logging_config import get_logger

log = get_logger(__name__)


def _tokenize(text: str) -> list[str]:
    return text.lower().split()


class BM25Index:
    """Keyword index over chunk texts. BM25 has no incremental delete,
    so we rebuild from the full corpus on each index() call."""

    def __init__(self, index_path: str | None = None):
        settings = get_settings()
        self._path = Path(index_path or settings.bm25_index_path)
        self._bm25: BM25Okapi | None = None
        self._ids: list[str] = []  # parallel array: position i ↔ vector_id i

    def build(self, ids: list[str], texts: list[str]) -> None:
        self._ids = ids
        self._bm25 = BM25Okapi([_tokenize(t) for t in texts])
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "wb") as f:
            pickle.dump({"ids": self._ids, "texts": texts}, f)
        log.info("bm25_built", chunks=len(ids), path=str(self._path))

    def query(self, query: str, top_k: int) -> list[tuple[str, float]]:
        if self._bm25 is None:
            return []
        scores = self._bm25.get_scores(_tokenize(query))
        ranked = sorted(zip(self._ids, scores), key=lambda x: x[1], reverse=True)
        return ranked[:top_k]