from src.ingestion.chunkers.base import BaseChunker
from src.ingestion.chunkers.code import CodeChunker
from src.ingestion.chunkers.markdown import MarkdownChunker
from src.ingestion.chunkers.text import TextChunker
from src.ingestion.code import CodeIngester
from src.ingestion.models import Chunk, Document


class MixedChunker(BaseChunker):
    def __init__(self):
        self._code = CodeChunker()
        self._markdown = MarkdownChunker()
        self._text = TextChunker()

    def chunk(self, document: Document) -> list[Chunk]:
        extension = document.metadata.get("extension", "").lower()

        if extension in CodeIngester.extensions:
            return self._code.chunk(document)
        if extension in {".md", ".markdown", ".mdx"}:
            return self._markdown.chunk(document)
        return self._text.chunk(document)