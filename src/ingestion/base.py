
from abc import ABC, abstractmethod

from src.ingestion.models import Document


class BaseIngester(ABC):
    """Contract for all data source ingesters (GitHub, Markdown, Incidents)."""

    @abstractmethod
    def ingest(self, source: str) -> list[Document]:
        """Read raw data from `source` and return a list of Documents."""
        ...