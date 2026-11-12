import json

import ollama

from src.config import get_settings
from src.logging_config import get_logger
from src.retrieval.base import RetrievalResult

log = get_logger(__name__)

_PROMPT = """You are ranking search results. Given a query and {n} candidate
passages, return the indices of the passages ordered from most to least
relevant to the query.

Query: {query}

Passages:
{passages}

Respond with ONLY a JSON array of indices, e.g. [2, 0, 4, 1, 3].
Include every index 0-{last} exactly once."""


class LLMReranker:
    """Listwise re-ranking: one LLM call scores all candidates at once."""

    def __init__(self, model: str | None = None):
        settings = get_settings()
        self._model = model or settings.llm_model
        self._client = ollama.Client(host=settings.ollama_base_url)

    def rerank(self, query: str, candidates: list[RetrievalResult]) -> list[RetrievalResult]:
        if len(candidates) <= 1:
            return candidates

        passages = "\n\n".join(
            f"[{i}] {r.content[:800]}" for i, r in enumerate(candidates)
        )
        try:
            resp = self._client.generate(
                model=self._model,
                prompt=_PROMPT.format(
                    n=len(candidates),
                    query=query,
                    passages=passages,
                    last=len(candidates) - 1,
                ),
            )
            order = json.loads(resp.response.strip())
            if not _is_permutation(order, len(candidates)):
                raise ValueError(f"bad permutation: {order}")
            return [candidates[i] for i in order]
        except Exception as exc:  # noqa: BLE001 — rerank is best-effort; bad LLM output falls back to RRF order
            log.warning("rerank_failed_fallback_to_rrf", error=str(exc))
            return candidates  # fall back to the RRF ordering


def _is_permutation(order: list, n: int) -> bool:
    return sorted(order) == list(range(n))