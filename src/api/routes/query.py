import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from src.api.deps import get_rag
from src.api.models.request import QueryRequest
from src.api.models.response import QueryResponse, SourceOut
from src.generation.generator import _REFUSAL, RAGGenerator
from src.generation.guardrails import confidence_label, grounding_score
from src.generation.prompt_templates import build_messages
from src.generation.response_builder import build_response
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
        results, conf, confident = rag.retriever.retrieve(req.query, filters)
        if not confident or not results:
            yield _sse("token", _REFUSAL)
            yield _sse("sources", [])
            yield _sse("done", {"confidence": "none", "refused": True, "retrieval_confidence": conf})
            return

        messages = build_messages(req.query, results, rag.memory.get(req.session_id))
        parts: list[str] = []
        for token in rag.llm.chat_stream(messages):
            parts.append(token)
            yield _sse("token", token)

        answer = "".join(parts)
        resp = build_response(answer, results)
        if not resp.refused:
            rag.memory.add_turn(req.session_id, req.query, answer)

        yield _sse("sources", [
            SourceOut(
                index=s.index,
                vector_id=s.vector_id,
                path=s.path,
                snippet=s.text[:200],
                score=results[s.index - 1].score,
            ).model_dump()
            for s in resp.sources
        ])
        yield _sse("done", {
            "confidence": confidence_label(conf, grounding_score(answer, results), resp.refused),
            "refused": resp.refused,
            "retrieval_confidence": conf,
        })

    return StreamingResponse(gen(), media_type="text/event-stream")


def _sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"