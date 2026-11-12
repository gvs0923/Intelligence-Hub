from src.retrieval.base import RetrievalResult

SYSTEM_PROMPT = """You are an Engineering Intelligence Assistant. Answer the
question using ONLY the provided context.

Rules:
- Cite every factual claim using [1], [2], etc. matching the context numbers
- Do NOT use any knowledge outside the provided context
- If the context doesn't contain enough information, respond with exactly:
  "I don't have enough information in the indexed sources to answer this."
- Keep the answer concise and technical"""


def format_context(results: list[RetrievalResult]) -> str:
    """Number the retrieved chunks [1..n] with their source metadata.
    The numbers here are the citation keys the LLM is told to use."""
    blocks = []
    for i, r in enumerate(results, 1):
        meta = r.metadata
        source = meta.get("source_path") or meta.get("vector_id", "unknown")
        header = f'[{i}] {{source: "{source}"'
        if meta.get("language"):
            header += f', language: "{meta["language"]}"'
        if meta.get("severity"):
            header += f', severity: "{meta["severity"]}"'
        header += "}"
        blocks.append(f"{header}\n{r.content}")
    return "\n\n".join(blocks)


def build_messages(
    query: str,
    results: list[RetrievalResult],
    history: list[dict] | None = None,
) -> list[dict]:
    """Assemble the chat message list: system + history + context + question."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history or [])
    user = (
        f"Context:\n{format_context(results)}\n\n"
        f"Question: {query}"
    )
    messages.append({"role": "user", "content": user})
    return messages