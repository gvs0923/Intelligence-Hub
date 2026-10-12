from src.db.models import Chunk as ChunkRow
from src.db.models import Document as DocumentRow
from src.db.models import IngestionJob
from src.ingestion.markdown import MarkdownIngester
from src.ingestion.chunkers.markdown import MarkdownChunker
from src.ingestion.pipeline import IngestionPipeline


def _make_pipeline(db_session):
    return IngestionPipeline(MarkdownIngester(), MarkdownChunker(), db_session)


def _run(db_session, data_source):
    job = IngestionJob(data_source_id=data_source.id)
    db_session.add(job)
    db_session.flush()
    return _make_pipeline(db_session).run(job)


def test_first_run_creates_documents_and_chunks(db_session, data_source, tmp_path):
    (tmp_path / "a.md").write_text("# A\nhello")

    job = _run(db_session, data_source)

    assert job.status == "done"
    assert db_session.query(DocumentRow).count() == 1
    assert db_session.query(ChunkRow).count() == 1


def test_second_run_skips_unchanged_file(db_session, data_source, tmp_path):
    (tmp_path / "a.md").write_text("# A\nhello")
    _run(db_session, data_source)

    job2 = _run(db_session, data_source)

    assert job2.status == "done"
    assert db_session.query(DocumentRow).count() == 1  # not duplicated
    assert db_session.query(ChunkRow).count() == 1      # no new chunks


def test_editing_file_triggers_rechunk(db_session, data_source, tmp_path):
    f = tmp_path / "a.md"
    f.write_text("# A\nhello")
    _run(db_session, data_source)

    f.write_text("# A\nhello\n\n## B\nworld")  # now 2 sections
    _run(db_session, data_source)

    assert db_session.query(DocumentRow).count() == 1   # same document
    assert db_session.query(ChunkRow).count() == 2       # chunks replaced, not accumulated


def test_bad_location_fails_job_without_crashing(db_session, data_source):
    data_source.location = "/path/does/not/exist"
    job = _run(db_session, data_source)

    assert job.status == "failed"
    assert job.error_message is not None