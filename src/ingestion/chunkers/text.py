from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.config import get_settings
from src.ingestion.chunkers.base import BaseChunker
from src.ingestion.models import Chunk, Document


class TextChunker(BaseChunker):
    """Generic text splitter — paragraph > line > word > character fallback."""

    def __init__(self):
        settings = get_settings()
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
        )

    def chunk(self, document: Document) -> list[Chunk]:
        return [
            Chunk(
                content=text,
                document=document,
                chunk_index=i,
                metadata={**document.metadata},
            )
            for i, text in enumerate(self._splitter.split_text(document.content))
        ]