from datetime import datetime

from pydantic import BaseModel


class SourceOut(BaseModel):
    index: int        # the [n] citation marker
    vector_id: str
    path: str
    snippet: str      # first ~200 chars of the cited chunk


class QueryResponse(BaseModel):
    answer: str
    sources: list[SourceOut]
    refused: bool
    confidence: str                    # high | medium | low | none
    retrieval_confidence: float


class DataSourceOut(BaseModel):
    id: int
    name: str
    source_type: str
    location: str
    created_at: datetime
    document_count: int = 0


class StatsResponse(BaseModel):
    total_chunks: int
    total_documents: int
    total_sources: int
    chroma_vectors: int
    bm25_loaded: bool
    index_drift: int                   # sqlite_chunks - chroma_vectors (should be 0)


class HealthResponse(BaseModel):
    status: str                        # ok | degraded
    ollama: bool
    chroma: bool
    sqlite: bool
    bm25: bool