from src.config import get_settings
from src.indexing.base import BaseEmbedder
from src.logging_config import get_logger

log = get_logger(__name__)


class SentenceTransformerEmbedder(BaseEmbedder):
    """Local fallback when Ollama is unreachable. Slower, different dims."""

    def __init__(self, model: str | None = None):
        from sentence_transformers import SentenceTransformer  # lazy import — heavy dep

        settings = get_settings()
        self._model_name = model or settings.fallback_embedding_model
        self._model = SentenceTransformer(self._model_name)

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model.encode(texts, convert_to_numpy=True)
        log.info("embedded_fallback", model=self._model_name, count=len(texts))
        return vectors.tolist()

    @property
    def dimension(self) -> int:
        return get_settings().fallback_embedding_dim