from fastapi.testclient import TestClient

from src.api import main


def test_lifespan_initializes_database_and_exposes_liveness(monkeypatch):
    initialized = []
    monkeypatch.setattr(main, "init_db", lambda: initialized.append(True))

    with TestClient(main.app) as client:
        live = client.get("/api/live")
        schema = client.get("/openapi.json")

    assert initialized == [True]
    assert live.status_code == 200
    assert live.json() == {"status": "alive"}
    assert schema.status_code == 200
    assert "/api/query" in schema.json()["paths"]