from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.api.deps import get_db
from src.api.models.response import HealthResponse, QueryLogOut, StatsResponse
from src.db.models import Chunk, DataSource, Document, QueryLog
from src.indexing.bm25 import BM25Index
from src.indexing.vector_store import VectorStore
from src.logging_config import get_logger

log = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/stats", response_model=StatsResponse)
def stats(db: Session = Depends(get_db)):
    sqlite_chunks = db.execute(select(func.count()).select_from(Chunk)).scalar_one()
    chroma_count = VectorStore().count()
    bm25_loaded = BM25Index().load()  # loads corpus into memory as a side effect
    return StatsResponse(
        total_chunks=sqlite_chunks,
        total_documents=db.execute(select(func.count()).select_from(Document)).scalar_one(),
        total_sources=db.execute(select(func.count()).select_from(DataSource)).scalar_one(),
        chroma_vectors=chroma_count,
        bm25_loaded=bm25_loaded,
        index_drift=sqlite_chunks - chroma_count,
    )


@router.get("/analytics/queries", response_model=list[QueryLogOut])
def query_history(
    hours: int = Query(24, ge=1, le=720),
    limit: int = Query(1000, ge=1, le=10_000),
    db: Session = Depends(get_db),
):
    since = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=hours)  # created_at is naive UTC
    rows = db.scalars(
        select(QueryLog)
        .where(QueryLog.created_at >= since)
        .order_by(QueryLog.created_at.desc())
        .limit(limit)
    ).all()
    return [
        QueryLogOut(
            time=r.created_at, query=r.query, latency_s=r.latency_s, confidence=r.confidence,
            sources=r.sources_cited, refused=r.refused, filter=r.source_type or "all",
        )
        for r in reversed(rows)
    ]


@router.get("/health", response_model=HealthResponse)
def health(db: Session = Depends(get_db)):
    """Deep health: every dependency the query path needs."""
    def probe(name: str, check) -> bool:
        try:
            check()
            return True
        except Exception as exc:  # noqa: BLE001 — health probe: any failure means 'down'
            log.warning("health_probe_failed", component=name, error=str(exc))
            return False

    def check_ollama() -> None:
        import ollama

        from src.config import get_settings
        ollama.Client(host=get_settings().ollama_base_url).list()

    ollama_ok = probe("ollama", check_ollama)
    chroma_ok = probe("chroma", lambda: VectorStore().count())
    sqlite_ok = probe("sqlite", lambda: db.execute(select(func.count()).select_from(Chunk)))
    bm25_ok = BM25Index().load()

    all_ok = all([ollama_ok, chroma_ok, sqlite_ok, bm25_ok])
    return HealthResponse(
        status="ok" if all_ok else "degraded",
        ollama=ollama_ok, chroma=chroma_ok, sqlite=sqlite_ok, bm25=bm25_ok,
    )