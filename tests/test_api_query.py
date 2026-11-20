from unittest.mock import Mock

from fastapi.testclient import TestClient

from src.api.deps import get_rag
from src.api.main import app
from src.retrieval.base import RetrievalResult
from src.ui.api_client import parse_sse


class FakeSource:
    def __init__(self, i):
        self.index, self.vector_id, self.path, self.text = i, f"v{i}", f"docs/f{i}.md", "x" * 250


def _fake_rag(refused=False):
    rag = Mock()
    if refused:
        resp = Mock(answer="I don't have enough information...", sources=[], refused=True,
                    confidence="none", retrieval_confidence=0.05)
    else:
        resp = Mock(answer="Pods evict under memory pressure [1].", sources=[FakeSource(1)],
                    refused=False, confidence="high", retrieval_confidence=0.9)
    rag.ask.return_value = resp
    return rag


def test_query_returns_cited_answer():
    app.dependency_overrides[get_rag] = lambda: _fake_rag()
    client = TestClient(app)
    r = client.post("/api/query", json={"query": "why evicted?", "session_id": "t"})
    app.dependency_overrides.clear()
    assert r.status_code == 200
    body = r.json()
    assert body["confidence"] == "high" and body["sources"][0]["path"] == "docs/f1.md"
    assert len(body["sources"][0]["snippet"]) == 200  # truncated


def test_query_refusal():
    app.dependency_overrides[get_rag] = lambda: _fake_rag(refused=True)
    client = TestClient(app)
    r = client.post("/api/query", json={"query": "quantum blockchain"})
    app.dependency_overrides.clear()
    assert r.json()["refused"] is True
    assert r.json()["confidence"] == "none"

def test_query_stream_emits_tokens_sources_done_and_saves_memory():
    rag = Mock()
    result = RetrievalResult(
        content="pods evict under memory pressure",
        score=0.03,
        metadata={"vector_id": "v1", "source_path": "docs/evict.md"},
    )
    rag.retriever.retrieve.return_value = ([result], 0.9, True)
    rag.memory.get.return_value = []
    rag.llm.chat_stream.return_value = iter(["Pods evict\n", "under memory pressure [1]."])
    app.dependency_overrides[get_rag] = lambda: rag
    client = TestClient(app)
    r = client.post("/api/query/stream", json={"query": "why evicted?", "session_id": "t"})
    app.dependency_overrides.clear()

    events = list(parse_sse(r.text.splitlines()))
    assert "".join(d for e, d in events if e == "token") == "Pods evict\nunder memory pressure [1]."
    sources = next(d for e, d in events if e == "sources")
    assert sources[0]["path"] == "docs/evict.md" and sources[0]["score"] == 0.03
    assert events[-1][0] == "done" and events[-1][1]["refused"] is False
    rag.memory.add_turn.assert_called_once()


def test_query_validation_422():
    app.dependency_overrides[get_rag] = lambda: _fake_rag()
    client = TestClient(app)
    status = client.post("/api/query", json={"query": ""}).status_code
    app.dependency_overrides.clear()
    assert status == 422