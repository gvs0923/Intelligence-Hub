import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from src.api.deps import get_rag
from src.api.models.request import QueryRequest
from src.api.models.response import QueryResponse, SourceOut
from src.generation.generator import RAGGenerator
from src.retrieval.filters import RetrievalFilters

router = APIRouter(prefix="/api", tags=["query"])


def _filters(req: QueryRequest) -> RetrievalFilters:
    return RetrievalFilters(
        source_type=req.source_type,
        repository=req.repository,
        language=req.language,
        severity=req.severity,
    )


@router.post("/query", response_model=QueryResponse)
def query(req: QueryRequest, rag: RAGGenerator = Depends(get_rag)) -> QueryResponse:
    resp = rag.ask(req.query, session_id=req.session_id, filters=_filters(req))
    return QueryResponse(
        answer=resp.answer,
        sources=[
            SourceOut(index=s.index, vector_id=s.vector_id, path=s.path, snippet=s.text[:200])
            for s in resp.sources
        ],
        refused=resp.refused,
        confidence=resp.confidence,
        retrieval_confidence=resp.retrieval_confidence,
    )


@router.post("/query/stream")
async def query_stream(req: QueryRequest, rag: RAGGenerator = Depends(get_rag)):
    """SSE stream: emits citation metadata first, then answer tokens.

    Event types:
      event: sources  — JSON array of cited sources (indices known only after
                        full generation; streamed answers can't cite reliably
                        mid-stream, so tokens are raw text)
      event: token    — one token chunk per SSE data line
      event: done     — final metadata {confidence, refused}
    """

    async def gen():
        # retrieval + generation are blocking -> run in threadpool
        results, _conf, confident = await run_in_threadpool(
            rag.retriever.retrieve, req.query, _filters(req)
        )
        from src.generation.prompt_templates import build_messages

        if not confident or not results:
            yield _sse("token", "I don't have enough information in the indexed sources to answer this.")
            yield _sse("done", {"confidence": "none", "refused": True})
            return

        messages = build_messages(req.query, results, rag.memory.get(req.session_id))
        for token in rag.llm.chat_stream(messages):
            yield _sse("token", token)
        yield _sse("done", {"confidence": "streamed", "refused": False})

    return StreamingResponse(gen(), media_type="text/event-stream")


def _sse(event: str, data) -> str:
    payload = data if isinstance(data, str) else json.dumps(data)
    return f"event: {event}\ndata: {payload}\n\n"