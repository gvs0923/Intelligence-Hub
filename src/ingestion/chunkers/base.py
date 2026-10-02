
from abc import ABC, abstractmethod

from src.ingestion.models import Chunk, Document


class BaseChunker(ABC):
    """Contract for all chunking strategies (text, markdown, code)."""

    @abstractmethod
    def chunk(self, document: Document) -> list[Chunk]:
        """Split a Document's content into one or more Chunks."""
        ...