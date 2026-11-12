from fastapi.testclient import TestClient

from src.api.main import app
from src.db.session import init_db

client = TestClient(app)


def test_health_reports_components():
    init_db()
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert set(body) >= {"status", "ollama", "chroma", "sqlite", "bm25"}
    assert body["sqlite"] is True


def test_sources_list_shape():
    init_db()
    r = client.get("/api/sources")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_delete_unknown_source_404():
    init_db()
    assert client.delete("/api/sources/999999").status_code == 404


def test_stats_shape():
    init_db()
    r = client.get("/api/stats")
    assert r.status_code == 200
    body = r.json()
    assert "index_drift" in body and "total_chunks" in body