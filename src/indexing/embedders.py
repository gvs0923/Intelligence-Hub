from src.indexing.base import BaseEmbedder
from src.logging_config import get_logger

log = get_logger(__name__)


def get_embedder() -> BaseEmbedder:
    """Primary = Ollama; falls back to sentence-transformers if unreachable."""
    from src.indexing.ollama import OllamaEmbedder

    embedder = OllamaEmbedder()
    try:
        embedder.embed(["health check"])  # one cheap call validates connectivity
        return embedder
    except Exception as exc:
        log.warning("ollama_unavailable_falling_back", error=str(exc))
        from src.indexing.fallback import SentenceTransformerEmbedder
        return SentenceTransformerEmbedder()