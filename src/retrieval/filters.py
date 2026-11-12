from dataclasses import dataclass

from src.retrieval.base import RetrievalResult


@dataclass
class RetrievalFilters:
    """User-supplied filters. All fields optional."""
    source_type: str | None = None   # "markdown" | "code" | "incident"
    repository: str | None = None
    language: str | None = None
    severity: str | None = None      # incidents only

    def to_chroma_where(self) -> dict | None:
        """Chroma `where` clause for the dense retriever."""
        clauses = [{k: v} for k, v in self._fields() if v is not None]
        if not clauses:
            return None
        return clauses[0] if len(clauses) == 1 else {"$and": clauses}

    def matches(self, r: RetrievalResult) -> bool:
        """Post-filter for BM25 results (BM25 has no where clause)."""
        return all(
            v is None or r.metadata.get(k) == v for k, v in self._fields()
        )

    def _fields(self):
        return [
            ("source_type", self.source_type),
            ("repository", self.repository),
            ("language", self.language),
            ("severity", self.severity),
        ]