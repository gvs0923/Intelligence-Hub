import json
import time

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from src.api.deps import get_rag
from src.api.models.request import QueryRequest
from src.api.models.response import QueryResponse, SourceOut
from src.db.models import QueryLog
from src.db.session import SessionLocal
from src.generation.generator import RAGGenerator, RAGResponse
from src.logging_config import get_logger
from src.retrieval.filters import RetrievalFilters

log = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["query"])


def _filters(req: QueryRequest) -> RetrievalFilters:
    return RetrievalFilters(
        source_type=req.source_type,
        repository=req.repository,
        language=req.language,
        severity=req.severity,
    )


def _sources(resp: RAGResponse) -> list[SourceOut]:
    return [
        SourceOut(index=s.index, vector_id=s.vector_id, path=s.path, snippet=s.text[:200], score=s.score)
        for s in resp.sources
    ]


def _record(req: QueryRequest, endpoint: str, resp: RAGResponse, latency_s: float) -> None:
    try:
        with SessionLocal() as db:
            db.add(QueryLog(
                session_id=req.session_id, endpoint=endpoint, query=req.query,
                source_type=req.source_type, latency_s=latency_s, refused=resp.refused,
                confidence=resp.confidence, retrieval_confidence=resp.retrieval_confidence,
                sources_cited=len(resp.sources),
            ))
            db.commit()
    except Exception as exc:  # noqa: BLE001 — analytics is best-effort; never fail the answer
        log.warning("query_log_failed", error=str(exc))


@router.post("/query", response_model=QueryResponse)
def query(req: QueryRequest, rag: RAGGenerator = Depends(get_rag)) -> QueryResponse:
    start = time.perf_counter()
    resp = rag.ask(req.query, session_id=req.session_id, filters=_filters(req))
    _record(req, "query", resp, time.perf_counter() - start)
    return QueryResponse(
        answer=resp.answer,
        sources=_sources(resp),
        refused=resp.refused,
        confidence=resp.confidence,
        retrieval_confidence=resp.retrieval_confidence,
    )


@router.post("/query/stream")
def query_stream(req: QueryRequest, rag: RAGGenerator = Depends(get_rag)) -> StreamingResponse:
    """SSE stream. Every `data:` payload is JSON, so newlines inside tokens survive.

    Event types, in order:
      event: token    — JSON string, one chunk of answer text (repeated)
      event: sources  — JSON array of cited sources; sent after generation because
                        [n] markers are only known once the full answer exists
      event: done     — {confidence, refused, retrieval_confidence}
    """
    filters = _filters(req)

    def gen():
        start = time.perf_counter()
        for item in rag.ask_stream(req.query, session_id=req.session_id, filters=filters):
            if isinstance(item, str):
                yield _sse("token", item)
                continue
            yield _sse("sources", [s.model_dump() for s in _sources(item)])
            yield _sse("done", {
                "confidence": item.confidence,
                "refused": item.refused,
                "retrieval_confidence": item.retrieval_confidence,
            })
            _record(req, "stream", item, time.perf_counter() - start)

    return StreamingResponse(gen(), media_type="text/event-stream")


def _sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"
