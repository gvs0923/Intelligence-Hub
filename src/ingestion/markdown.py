from typing import ClassVar

from src.ingestion.local import LocalDirectoryIngester


class MarkdownIngester(LocalDirectoryIngester):
    extensions: ClassVar[set[str]] = {".md", ".markdown", ".mdx"}
    source_type = "markdown"