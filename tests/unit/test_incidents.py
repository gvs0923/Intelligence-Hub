import json

import pytest
from pydantic import ValidationError

from src.ingestion.chunkers.incident import IncidentChunker
from src.ingestion.incident import IncidentIngester
from src.ingestion.registry import get_chunker, get_ingester


def test_json_incidents_and_field_chunks(tmp_path):
    path = tmp_path / "incidents.json"
    path.write_text(
        json.dumps(
            [
                {
                    "id": "INC-001",
                    "title": " Login failure ",
                    "description": "Users could not sign in.",
                    "root_cause": "Connection pool exhausted.",
                    "resolution": "Increased pool capacity.",
                    "severity": "P1",
                },
                {
                    "id": "INC-002",
                    "title": "Slow requests",
                    "description": "Requests exceeded the timeout.",
                },
            ]
        ),
        encoding="utf-8",
    )

    documents = IncidentIngester().ingest(str(path))

    assert len(documents) == 2
    assert documents[0].source_path != documents[1].source_path
    assert documents[0].metadata["title"] == "Login failure"

    chunks = IncidentChunker().chunk(documents[0])

    assert len(chunks) == 3
    assert [chunk.chunk_index for chunk in chunks] == [0, 1, 2]
    assert [chunk.metadata["incident_field"] for chunk in chunks] == [
        "description",
        "root_cause",
        "resolution",
    ]
    assert all(chunk.metadata["severity"] == "P1" for chunk in chunks)
    assert all(chunk.document == documents[0] for chunk in chunks)


def test_csv_incident_normalizes_missing_values(tmp_path):
    path = tmp_path / "incidents.csv"
    path.write_text(
        "title,description,severity,timestamp\n"
        "Database timeout,Queries timed out,,\n",
        encoding="utf-8",
    )

    documents = IncidentIngester().ingest(str(path))

    assert len(documents) == 1
    assert documents[0].metadata["severity"] is None
    assert documents[0].metadata["timestamp"] is None


def test_invalid_incident_is_rejected(tmp_path):
    path = tmp_path / "invalid.json"
    path.write_text(
        json.dumps({"title": "   ", "description": "An outage occurred."}),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError):
        IncidentIngester().ingest(str(path))


def test_duplicate_incident_ids_are_rejected(tmp_path):
    path = tmp_path / "duplicates.json"
    record = {
        "id": "INC-001",
        "title": "Login failure",
        "description": "Users could not sign in.",
    }
    path.write_text(json.dumps([record, record]), encoding="utf-8")

    with pytest.raises(ValueError, match="Duplicate incident identity"):
        IncidentIngester().ingest(str(path))


def test_incident_registry():
    assert isinstance(get_ingester("incident"), IncidentIngester)
    assert isinstance(get_chunker("incident"), IncidentChunker)