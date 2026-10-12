from pathlib import Path
from typing import ClassVar

from src.ingestion.base import BaseIngester
from src.ingestion.models import Document

SKIP_DIRS = {"__pycache__", "node_modules", "venv", "dist", "build"}


def _is_skipped(path: Path, root: Path) -> bool:
    """True if any directory component between root and path is hidden (dotfile) or junk."""
    rel_parts = path.relative_to(root).parts[:-1]  # directories only, not the filename itself
    return any(part.startswith(".") or part in SKIP_DIRS for part in rel_parts)


def _iter_files(root: Path, extensions: set[str]):
    """Yield files under root matching extensions, skipping junk/hidden dirs."""
    for path in sorted(root.rglob("*")):
        if path.is_dir():
            continue
        if _is_skipped(path, root):
            continue
        if path.suffix.lower() in extensions:
            yield path


class LocalDirectoryIngester(BaseIngester):
    """Base for ingesters that read files from a local directory."""

    extensions: ClassVar[set[str]] = set()
    source_type: str = "text"

    def ingest(self, source: str) -> list[Document]:
        root = Path(source)
        if not root.is_dir():
            raise ValueError(f"Not a directory: {source}")

        documents = []
        for path in _iter_files(root, self.extensions):
            documents.append(
                Document(
                    content=path.read_text(encoding="utf-8", errors="replace"),
                    source_type=self.source_type,
                    source_path=str(path),
                    metadata={"filename": path.name, "extension": path.suffix},
                )
            )
        return documents