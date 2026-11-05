from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from kombu.exceptions import OperationalError
from sqlalchemy import func, select

from src.api.routes.ingest import IngestRequest, refresh_source, trigger_ingest
from src.db.models import DataSource, IngestionJob


def test_create_incident_source(db_session, monkeypatch):
    publish = Mock()
    monkeypatch.setattr(
        "src.api.routes.ingest.run_ingestion.delay",
        publish,
    )

    result = trigger_ingest(
        IngestRequest(
            name="incidents",
            source_type="incident",
            location="/tmp/incidents.json",
        ),
        db=db_session,
    )

    source = db_session.get(DataSource, result["data_source_id"])
    assert source.source_type == "incident"
    assert result["status"] == "queued"
    publish.assert_called_once_with(result["job_id"])


def test_refresh_reuses_source(db_session, data_source, monkeypatch):
    publish = Mock()
    monkeypatch.setattr(
        "src.api.routes.ingest.run_ingestion.delay",
        publish,
    )

    first = refresh_source(data_source.id, db=db_session)
    second = refresh_source(data_source.id, db=db_session)

    assert first["data_source_id"] == second["data_source_id"]
    assert first["job_id"] != second["job_id"]
    assert db_session.scalar(
        select(func.count()).select_from(DataSource)
    ) == 1
    assert publish.call_count == 2


def test_refresh_missing_source(db_session):
    with pytest.raises(HTTPException) as error:
        refresh_source(999, db=db_session)

    assert error.value.status_code == 404


def test_invalid_source_creates_no_rows(db_session):
    with pytest.raises(HTTPException) as error:
        trigger_ingest(
            IngestRequest(
                name="invalid",
                source_type="unknown",
                location="/tmp",
            ),
            db=db_session,
        )

    assert error.value.status_code == 400
    assert db_session.scalar(
        select(func.count()).select_from(DataSource)
    ) == 0


def test_queue_failure_marks_job_failed(db_session, data_source, monkeypatch):
    publish = Mock(side_effect=OperationalError("Broker unavailable"))
    monkeypatch.setattr(
        "src.api.routes.ingest.run_ingestion.delay",
        publish,
    )

    with pytest.raises(HTTPException) as error:
        refresh_source(data_source.id, db=db_session)

    assert error.value.status_code == 503
    job = db_session.scalar(select(IngestionJob))
    assert job.status == "failed"
    assert job.error_message == "Could not publish ingestion task"