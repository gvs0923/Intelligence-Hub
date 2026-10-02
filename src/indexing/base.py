
from abc import ABC, abstractmethod


class BaseEmbedder(ABC):
    """Contract for embedding providers (Ollama, sentence-transformers)."""

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text."""
        ...

    @property
    @abstractmethod
    def dimension(self) -> int:
        """The dimensionality of vectors this embedder produces."""
        ...