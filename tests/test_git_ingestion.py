from git import Actor, Repo

from src.ingestion.chunkers.mixed import MixedChunker
from src.ingestion.git_repo import GitRepoIngester


def test_git_clone_pull_and_mixed_chunking(tmp_path):
    origin = tmp_path / "origin"
    origin.mkdir()
    repo = Repo.init(origin)

    (origin / "service.py").write_text(
        "def health():\n    return 'ok'\n",
        encoding="utf-8",
    )
    (origin / "README.md").write_text(
        "# Service\n\nHealth check documentation.\n",
        encoding="utf-8",
    )

    actor = Actor("Test Author", "test@example.invalid")
    repo.index.add(["service.py", "README.md"])
    repo.index.commit(
        "Initial fixture",
        author=actor,
        committer=actor,
    )

    ingester = GitRepoIngester(local_root=str(tmp_path / "clones"))
    documents = ingester.ingest(str(origin))
    code = next(
        document
        for document in documents
        if document.metadata["extension"] == ".py"
    )

    chunks = MixedChunker().chunk(code)
    assert any(chunk.metadata.get("symbol") == "health" for chunk in chunks)
    assert code.metadata["commit_sha"] == repo.head.commit.hexsha

    (origin / "service.py").write_text(
        "def health():\n    return 'updated'\n",
        encoding="utf-8",
    )
    repo.index.add(["service.py"])
    repo.index.commit(
        "Update fixture",
        author=actor,
        committer=actor,
    )

    updated = ingester.ingest(str(origin))
    updated_code = next(
        document
        for document in updated
        if document.metadata["extension"] == ".py"
    )

    assert "'updated'" in updated_code.content
    assert updated_code.metadata["commit_sha"] == repo.head.commit.hexsha


def test_repositories_with_same_name_have_different_clone_paths(tmp_path):
    ingester = GitRepoIngester(local_root=str(tmp_path))

    first = ingester._local_path("/team-a/backend")
    second = ingester._local_path("/team-b/backend")

    assert first != second