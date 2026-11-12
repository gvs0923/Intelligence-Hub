import ollama

from src.config import get_settings
from src.logging_config import get_logger

log = get_logger(__name__)

_PROMPT = """You are a search query expander. Rewrite the user's query into a
better keyword/semantic search query for an engineering knowledge base of
docs, source code, and incident reports.

Rules:
- Keep it under 25 words
- Add relevant technical synonyms (e.g. "auth" -> "authentication login")
- Do NOT answer the query
- Output ONLY the rewritten query, nothing else

Query: {query}"""


class QueryRewriter:
    """Uses the local LLM to expand short/ambiguous queries."""

    def __init__(self, model: str | None = None):
        settings = get_settings()
        self._model = model or settings.llm_model
        self._client = ollama.Client(host=settings.ollama_base_url)

    def rewrite(self, query: str) -> str:
        # Very short queries benefit most from expansion; long ones are already specific
        if len(query.split()) >= 8:
            return query
        try:
            resp = self._client.generate(model=self._model, prompt=_PROMPT.format(query=query))
            rewritten = resp.response.strip().strip('"')
            log.info("query_rewritten", original=query, rewritten=rewritten)
            return rewritten or query
        except Exception as exc:  # noqa: BLE001 — LLM call must never break retrieval; always fall back
            log.warning("query_rewrite_failed", error=str(exc))
            return query  # graceful degradation: original query is always safe