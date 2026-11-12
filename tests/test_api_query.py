from unittest.mock import Mock

from fastapi.testclient import TestClient

from src.api.deps import get_rag
from src.api.main import app


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


def test_query_validation_422():
    client = TestClient(app)
    assert client.post("/api/query", json={"query": ""}).status_code == 422