from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.config import Settings
from src.generation.llm_client import LLMClient
from src.indexing.vector_store import VectorStore
from src.retrieval.base import RetrievalResult
from src.retrieval.query_rewriter import QueryRewriter
from src.retrieval.reranker import LLMReranker
from src.tasks.ingestion_tasks import run_ingestion


def test_llm_accepts_empty_content_and_skips_empty_stream_chunks(monkeypatch):
    client = Mock()
    monkeypatch.setattr("src.generation.llm_client.ollama.Client", lambda **kwargs: client)
    llm = LLMClient()
    client.chat.return_value = SimpleNamespace(message=SimpleNamespace(content=None))
    assert llm.chat([]) == ""

    client.chat.return_value = iter([
        SimpleNamespace(message=SimpleNamespace(content=None)),
        SimpleNamespace(message=SimpleNamespace(content="answer")),
        SimpleNamespace(message=SimpleNamespace(content="")),
    ])
    assert list(llm.chat_stream([])) == ["answer"]


@pytest.mark.parametrize("content", [None, "", '"pod eviction memory"'])
def test_rewriter_handles_optional_model_output(monkeypatch, content):
    client = Mock()
    client.generate.return_value = SimpleNamespace(response=content)
    monkeypatch.setattr("src.retrieval.query_rewriter.ollama.Client", lambda **kwargs: client)
    expected = "pod eviction memory" if content else "pod eviction"
    assert QueryRewriter().rewrite("pod eviction") == expected


def test_reranker_falls_back_for_empty_model_output(monkeypatch):
    client = Mock()
    client.generate.return_value = SimpleNamespace(response=None)
    monkeypatch.setattr("src.retrieval.reranker.ollama.Client", lambda **kwargs: client)
    candidates = [RetrievalResult(content=text, score=1) for text in ("first", "second")]
    assert LLMReranker().rerank("query", candidates) == candidates


def test_missing_ingestion_job_closes_session(monkeypatch):
    db = Mock()
    db.get.return_value = None
    monkeypatch.setattr("src.tasks.ingestion_tasks.SessionLocal", lambda: db)
    with pytest.raises(ValueError, match="does not exist"):
        run_ingestion.run(123)
    db.close.assert_called_once()


def test_vector_store_selects_http_client_and_handles_missing_metadata(monkeypatch):
    client = Mock()
    client.get_or_create_collection.return_value.metadata = None
    http_client = Mock(return_value=client)
    persistent_client = Mock(return_value=client)
    monkeypatch.setattr("src.indexing.vector_store.chromadb.HttpClient", http_client)
    monkeypatch.setattr("src.indexing.vector_store.chromadb.PersistentClient", persistent_client)
    monkeypatch.setattr(
        "src.indexing.vector_store.get_settings",
        lambda: Settings(_env_file=None, chroma_host="chroma"),
    )

    assert VectorStore().dimension is None
    http_client.assert_called_once_with(host="chroma", port=8000)
    VectorStore("explicit-local-path")
    persistent_client.assert_called_once_with(path="explicit-local-path")
