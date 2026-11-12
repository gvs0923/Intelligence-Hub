import re

from pydantic import BaseModel

from src.retrieval.base import RetrievalResult

_CITATION_RE = re.compile(r"\[(\d+)\]")

_REFUSAL = "I don't have enough information in the indexed sources"


class Source(BaseModel):
    index: int          # the [n] number shown to the user
    vector_id: str
    path: str
    text: str


class GenerationResponse(BaseModel):
    answer: str
    sources: list[Source]
    refused: bool       # True when the model gave the "don't know" response


def build_response(answer: str, results: list[RetrievalResult]) -> GenerationResponse:
    """Extract [n] citation markers from the answer and map each back to the
    retrieved chunk it refers to."""
    refused = _REFUSAL.lower() in answer.lower()

    cited: list[Source] = []
    seen: set[int] = set()
    for match in _CITATION_RE.finditer(answer):
        idx = int(match.group(1))
        if idx in seen or not (1 <= idx <= len(results)):
            continue  # dedupe + drop hallucinated indices like [9] with only 5 chunks
        seen.add(idx)
        r = results[idx - 1]
        cited.append(
            Source(
                index=idx,
                vector_id=r.metadata.get("vector_id", ""),
                path=r.metadata.get("source_path", r.metadata.get("vector_id", "unknown")),
                text=r.content,
            )
        )

    return GenerationResponse(
        answer=answer,
        sources=sorted(cited, key=lambda s: s.index),
        refused=refused,
    )