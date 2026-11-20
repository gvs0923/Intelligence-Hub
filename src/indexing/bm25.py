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
        self._mtime_ns: int | None = None

    def build(self, ids: list[str], texts: list[str]) -> None:
        self._ids = ids
        self._bm25 = BM25Okapi([_tokenize(t) for t in texts])
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "wb") as f:
            pickle.dump({"ids": self._ids, "texts": texts}, f)
        self._mtime_ns = self._path.stat().st_mtime_ns
        log.info("bm25_built", chunks=len(ids), path=str(self._path))

    def load(self) -> bool:
        """Rebuild the in-memory index from the pickled corpus.

        Returns False if no index file exists yet.
        """
        if not self._path.exists():
            log.warning("bm25_index_missing", path=str(self._path))
            return False
        with open(self._path, "rb") as f:
            data = pickle.load(f)
        self._ids = data["ids"]
        self._bm25 = BM25Okapi([_tokenize(t) for t in data["texts"]])
        self._mtime_ns = self._path.stat().st_mtime_ns
        log.info("bm25_loaded", chunks=len(self._ids))
        return True

    def refresh(self) -> None:
        """Reload if another process (e.g. the Celery worker) rewrote the pickle."""
        if self._path.exists() and self._path.stat().st_mtime_ns != self._mtime_ns:
            self.load()

    def query(self, query: str, top_k: int) -> list[tuple[str, float]]:
        if self._bm25 is None:
            return []
        scores = self._bm25.get_scores(_tokenize(query))
        ranked = sorted(zip(self._ids, scores), key=lambda x: x[1], reverse=True)
        return ranked[:top_k]