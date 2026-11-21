from src.db.models import Chunk as ChunkRow
from src.db.models import DataSource, IngestionJob
from src.db.models import Document as DocumentRow
from src.ingestion.chunkers.code import CodeChunker
from src.ingestion.chunkers.markdown import MarkdownChunker
from src.ingestion.code import CodeIngester
from src.ingestion.markdown import MarkdownIngester
from src.ingestion.pipeline import IngestionPipeline


def _make_pipeline(db_session):
    return IngestionPipeline(MarkdownIngester(), MarkdownChunker(), db_session)


def _run(db_session, data_source, force=False):
    job = IngestionJob(data_source_id=data_source.id)
    db_session.add(job)
    db_session.flush()
    return _make_pipeline(db_session).run(job, force=force)


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

def test_chunk_text_and_metadata_survive_save_and_reload(db_session, data_source, tmp_path):
    (tmp_path / "a.md").write_text("# Title\n\nSome body text.")
    _run(db_session, data_source)

    db_session.expunge_all()  # force reload from DB, not session cache
    row = db_session.query(ChunkRow).one()

    assert "Some body text." in row.text
    assert isinstance(row.chunk_metadata, dict)


def test_chunks_carry_filter_metadata(db_session, tmp_path):
    ds = DataSource(name="java-client", source_type="code", location=str(tmp_path))
    db_session.add(ds)
    db_session.flush()
    (tmp_path / "A.java").write_text("public class A {}")
    job = IngestionJob(data_source_id=ds.id)
    db_session.add(job)
    db_session.flush()

    IngestionPipeline(CodeIngester(), CodeChunker(), db_session).run(job)

    meta = db_session.query(ChunkRow).first().chunk_metadata
    assert meta["repository"] == "java-client"
    assert meta["language"] == "java"
    assert "severity" not in meta


def test_force_rewrites_unchanged_file(db_session, data_source, tmp_path):
    (tmp_path / "a.md").write_text("# A\nhello")
    _run(db_session, data_source)
    db_session.query(ChunkRow).one().chunk_metadata = {}  # simulate a chunk written by old code
    db_session.commit()

    _run(db_session, data_source)
    assert db_session.query(ChunkRow).one().chunk_metadata == {}  # same hash -> skipped

    _run(db_session, data_source, force=True)
    db_session.expunge_all()
    assert db_session.query(ChunkRow).one().chunk_metadata["source_type"] == "markdown"