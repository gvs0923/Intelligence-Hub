from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.api.deps import get_db
from src.api.models.response import DataSourceOut
from src.config import get_settings
from src.db.models import Chunk, DataSource, Document
from src.indexing.bm25 import BM25Index
from src.indexing.vector_store import VectorStore

router = APIRouter(prefix="/api/sources", tags=["sources"])


def _rebuild_bm25(db: Session) -> None:
    """BM25 is corpus-level — deleting chunks changes every score, so rebuild
    from whatever remains in SQLite. On an empty corpus, remove the pickle."""
    rows = db.execute(select(Chunk.vector_id, Chunk.text)).all()
    index = BM25Index()
    if rows:
        index.build([r[0] for r in rows], [r[1] for r in rows])
    else:
        path = Path(get_settings().bm25_index_path)
        path.unlink(missing_ok=True)  # empty corpus = no index, not an empty BM25


@router.get("", response_model=list[DataSourceOut])
def list_sources(db: Session = Depends(get_db)):
    rows = db.execute(
        select(
            DataSource,
            func.count(Document.id).label("doc_count"),
        )
        .outerjoin(Document, Document.data_source_id == DataSource.id)
        .group_by(DataSource.id)
    ).all()
    return [
        DataSourceOut(
            id=ds.id, name=ds.name, source_type=ds.source_type,
            location=ds.location, created_at=ds.created_at,
            document_count=count,
        )
        for ds, count in rows
    ]


@router.delete("/{source_id}", status_code=204)
def delete_source(source_id: int, db: Session = Depends(get_db)):
    """Remove a source and everything it indexed: Chroma vectors, SQLite
    chunks/documents, then rebuild the corpus-level BM25 index."""
    ds = db.get(DataSource, source_id)
    if ds is None:
        raise HTTPException(404, "Data source not found")

    vector_ids = [
        r[0]
        for r in db.execute(
            select(Chunk.vector_id)
            .join(Document, Document.id == Chunk.document_id)
            .where(Document.data_source_id == source_id)
        ).all()
    ]
    VectorStore().delete(vector_ids)  # vectors first: orphans are worse than missing

    # delete chunks -> documents -> source (no CASCADE in models, do it manually)
    doc_ids = [
        r[0] for r in db.execute(
            select(Document.id).where(Document.data_source_id == source_id)
        ).all()
    ]
    db.query(Chunk).filter(Chunk.document_id.in_(doc_ids)).delete(synchronize_session=False)
    db.query(Document).filter(Document.id.in_(doc_ids)).delete(synchronize_session=False)
    db.delete(ds)
    db.commit()

    _rebuild_bm25(db)  # after commit: BM25 reflects exactly what's in SQLite now