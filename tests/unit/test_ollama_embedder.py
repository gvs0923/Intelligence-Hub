from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.indexing.ollama import OllamaEmbedder


@pytest.mark.parametrize("size", [0, 1, 32, 33, 65])
def test_embedding_batches_preserve_order(monkeypatch, size):
    client = Mock()
    client.embed.side_effect = lambda *, model, input: SimpleNamespace(
        embeddings=[[float(text), 1.0] for text in input]
    )
    monkeypatch.setattr(
        "src.indexing.ollama.ollama.Client",
        lambda **kwargs: client,
    )

    texts = [str(index) for index in range(size)]
    result = OllamaEmbedder(model="test-model").embed(texts)

    assert result == [[float(index), 1.0] for index in range(size)]
    assert client.embed.call_count == (size + 31) // 32

    for call in client.embed.call_args_list:
        assert call.kwargs["model"] == "test-model"
        assert 1 <= len(call.kwargs["input"]) <= 32


def test_embedding_failure_is_not_silently_swallowed(monkeypatch):
    client = Mock()
    client.embed.side_effect = RuntimeError("embedding unavailable")
    monkeypatch.setattr(
        "src.indexing.ollama.ollama.Client",
        lambda **kwargs: client,
    )

    with pytest.raises(RuntimeError, match="embedding unavailable"):
        OllamaEmbedder().embed(["pod eviction"])