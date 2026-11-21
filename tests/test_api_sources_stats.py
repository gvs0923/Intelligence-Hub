from fastapi.testclient import TestClient

from src.api.main import app
from src.api.routes.stats import query_history
from src.db.models import QueryLog
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


def test_query_history_returns_recent_rows(db_session):
    db_session.add(QueryLog(
        session_id="s", endpoint="query", query="why evicted", source_type=None, latency_s=1.2,
        refused=False, confidence="high", retrieval_confidence=0.8, sources_cited=2,
    ))
    db_session.commit()
    rows = query_history(hours=1, limit=10, db=db_session)
    assert rows[0].query == "why evicted" and rows[0].filter == "all"