from pathlib import Path

from git import Repo

from src.ingestion.base import BaseIngester
from src.ingestion.code import CodeIngester
from src.ingestion.hashing import content_hash
from src.ingestion.local import _iter_files
from src.ingestion.models import Document

TEXT_EXTENSIONS = CodeIngester.extensions | {
    ".md", ".markdown", ".mdx", ".txt",
    ".toml", ".yaml", ".yml", ".json",
}


class GitRepoIngester(BaseIngester):
    """Clone (or update) a git repo and ingest its text files."""

    def __init__(self, local_root: str = "./data/repos"):
        self.local_root = Path(local_root)

    def ingest(self, source: str) -> list[Document]:
        repo_path = self._local_path(source)
        repo = self._clone_or_pull(source, repo_path)
        commit_sha = repo.head.commit.hexsha

        documents = []
        for path in _iter_files(repo_path, TEXT_EXTENSIONS):
            rel = path.relative_to(repo_path)
            extension = path.suffix.lower()
            documents.append(
                Document(
                    content=path.read_text(encoding="utf-8", errors="replace"),
                    source_type=(
                        "code" if extension in CodeIngester.extensions else "markdown"
                    ),
                    source_path=f"{source}::{rel}",
                    metadata={
                        "repo_url": source,
                        "relative_path": str(rel),
                        "commit_sha": commit_sha,
                        "filename": rel.name,
                        "extension": extension,
                    },
                )
            )
        return documents

    def _local_path(self, url: str) -> Path:
        name = url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git")
        return self.local_root / f"{name}-{content_hash(url)[:12]}"

    def _clone_or_pull(self, url: str, path: Path) -> Repo:
        if (path / ".git").exists():
            repo = Repo(path)
            repo.remotes.origin.pull()
            return repo
        path.parent.mkdir(parents=True, exist_ok=True)
        return Repo.clone_from(url, path)