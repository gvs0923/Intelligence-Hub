import ollama

from src.config import get_settings
from src.indexing.base import BaseEmbedder
from src.logging_config import get_logger

log = get_logger(__name__)

_EMBED_BATCH = 32  # texts per HTTP call — avoids 100s of round trips


class OllamaEmbedder(BaseEmbedder):
    """Embeds text via a locally-running Ollama instance."""

    def __init__(self, model: str | None = None):
        settings = get_settings()
        self._model = model or settings.embedding_model
        self._client = ollama.Client(host=settings.ollama_base_url)

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for i in range(0, len(texts), _EMBED_BATCH):
            batch = texts[i : i + _EMBED_BATCH]
            resp = self._client.embed(model=self._model, input=batch)
            vectors.extend(resp.embeddings)
        log.info("embedded_batch", model=self._model, count=len(texts))
        return vectors

    @property
    def dimension(self) -> int:
        return get_settings().embedding_dim