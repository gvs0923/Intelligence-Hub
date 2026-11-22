from collections.abc import Iterator

import ollama

from src.config import get_settings
from src.logging_config import get_logger

log = get_logger(__name__)


class LLMClient:
    """Chat wrapper around the local Ollama model.

    Two interfaces:
    - chat(): one-shot, returns the full response string
    - chat_stream(): yields token chunks for streaming UIs (Phase 8/Streamlit)
    """

    def __init__(self, model: str | None = None):
        settings = get_settings()
        self._model = model or settings.llm_model
        self._client = ollama.Client(host=settings.ollama_base_url)

    def chat(self, messages: list[dict], temperature: float = 0.1) -> str:
        resp = self._client.chat(
            model=self._model,
            messages=messages,
            options={"temperature": temperature},
        )
        content = resp.message.content or ""
        log.info("llm_response", model=self._model, chars=len(content))
        return content

    def chat_stream(self, messages: list[dict], temperature: float = 0.1) -> Iterator[str]:
        stream = self._client.chat(
            model=self._model,
            messages=messages,
            options={"temperature": temperature},
            stream=True,
        )
        for chunk in stream:
            if chunk.message.content:
                yield chunk.message.content