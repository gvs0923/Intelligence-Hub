import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.db.models import Base, DataSource


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