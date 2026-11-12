import re

from src.retrieval.base import RetrievalResult

_WORD_RE = re.compile(r"[a-z0-9_]+")
_STOP = {
    "the", "a", "an", "is", "are", "was", "were", "in", "on", "of", "to",
    "and", "or", "for", "with", "that", "this", "it", "by", "as", "at",
}


def _words(text: str) -> set[str]:
    return {w for w in _WORD_RE.findall(text.lower()) if w not in _STOP and len(w) > 2}


def grounding_score(answer: str, results: list[RetrievalResult]) -> float:
    """Fraction of content words in the answer that appear somewhere in the
    retrieved context. 1.0 = fully grounded; low = the answer contains words
    the sources never used (possible hallucination).

    This is a cheap lexical heuristic, not a factuality checker — proper nouns
    and paraphrases will legitimately score < 1."""
    answer_words = _words(answer)
    if not answer_words:
        return 1.0
    context_words = _words(" ".join(r.content for r in results))
    grounded = answer_words & context_words
    return len(grounded) / len(answer_words)


def confidence_label(retrieval_confidence: float, grounding: float, refused: bool) -> str:
    """Combine retrieval confidence + grounding into a user-facing level."""
    if refused:
        return "none"
    combined = retrieval_confidence * 0.5 + grounding * 0.5
    if combined >= 0.6:
        return "high"
    if combined >= 0.35:
        return "medium"
    return "low"