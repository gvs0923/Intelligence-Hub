from collections.abc import Generator

from sqlalchemy.orm import Session

from src.db.session import SessionLocal
from src.generation.generator import RAGGenerator
from src.generation.llm_client import LLMClient
from src.retrieval.pipeline import RetrievalPipeline

_rag: RAGGenerator | None = None


def get_db() -> Generator[Session, None, None]:
    """One SQLAlchemy session per request, always closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_rag() -> RAGGenerator:
    """Process-wide singleton RAGGenerator (owns ConversationMemory).
    Built lazily on first request so app startup stays fast and
    Ollama isn't required just to serve /health."""
    global _rag
    if _rag is None:
        _rag = RAGGenerator(RetrievalPipeline.from_defaults(), LLMClient())
    return _rag