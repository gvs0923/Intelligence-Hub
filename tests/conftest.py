import os
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.db.models import Base, DataSource


def pytest_sessionstart(session):
    storage = TemporaryDirectory(prefix="intelligencehub-tests-")
    session.config.add_cleanup(storage.cleanup)
    root = Path(storage.name)
    os.environ.update({
        "SQLITE_DB_PATH": str(root / "metadata.db"),
        "CHROMA_PERSIST_DIR": str(root / "chroma"),
        "BM25_INDEX_PATH": str(root / "bm25.pkl"),
        "CHROMA_HOST": "",
    })


@pytest.fixture
def db_session():
    """A fresh, isolated in-memory SQLite DB for each test."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def data_source(db_session, tmp_path):
    """A DataSource row pointing at a tmp_path directory."""
    ds = DataSource(name="test", source_type="markdown", location=str(tmp_path))
    db_session.add(ds)
    db_session.flush()
    return ds