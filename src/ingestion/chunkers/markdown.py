from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)

from src.config import get_settings
from src.ingestion.chunkers.base import BaseChunker
from src.ingestion.models import Chunk, Document

HEADERS = [("#", "h1"), ("##", "h2"), ("###", "h3")]


class MarkdownChunker(BaseChunker):
    """Split on headings first; fall back to text splitting for large sections."""

    def __init__(self):
        settings = get_settings()
        self._header_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=HEADERS)
        self._fallback = RecursiveCharacterTextSplitter(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
        )

    def chunk(self, document: Document) -> list[Chunk]:
        chunks: list[Chunk] = []
        for section in self._header_splitter.split_text(document.content):
            header_path = " > ".join(section.metadata.values())  # e.g. "API > Auth"
            for text in self._fallback.split_text(section.page_content):
                chunks.append(
                    Chunk(
                        content=text,
                        document=document,
                        chunk_index=len(chunks),
                        metadata={**document.metadata, "section": header_path},
                    )
                )
        return chunks