from typing import ClassVar

from src.ingestion.local import LocalDirectoryIngester


class CodeIngester(LocalDirectoryIngester):
    extensions: ClassVar[set[str]] = {".py", ".js", ".ts", ".jsx", ".tsx"}
    source_type = "code"