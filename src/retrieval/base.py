
from abc import ABC, abstractmethod

from pydantic import BaseModel


class RetrievalResult(BaseModel):
    content: str
    score: float
    metadata: dict = {}


class BaseRetriever(ABC):
    """Contract for retrieval strategies (dense, BM25, hybrid)."""

    @abstractmethod
    def retrieve(self, query: str, top_k: int) -> list[RetrievalResult]:
        """Return the top_k most relevant results for the query."""
        ...