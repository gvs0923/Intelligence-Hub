from src.ingestion.chunkers.code import CodeChunker
from src.ingestion.chunkers.markdown import MarkdownChunker
from src.ingestion.models import Document


def test_markdown_chunker_splits_on_headings():
    doc = Document(
        content="# Auth\nOAuth details here.\n\n## Tokens\nJWT expiry is 1h.",
        source_type="markdown",
        source_path="auth.md",
    )
    chunks = MarkdownChunker().chunk(doc)

    assert len(chunks) == 2
    assert "Auth" in chunks[0].metadata["section"]
    assert "Tokens" in chunks[1].metadata["section"]


def test_code_chunker_splits_on_function_and_class_boundaries():
    source = (
        "import os\n\n"
        "def add(a, b):\n    return a + b\n\n\n"
        "class Greeter:\n    def greet(self):\n        return 'hi'\n"
    )
    doc = Document(
        content=source,
        source_type="code",
        source_path="sample.py",
        metadata={"extension": ".py"},
    )
    chunks = CodeChunker().chunk(doc)

    symbols = {c.metadata.get("symbol") for c in chunks}
    assert "add" in symbols
    assert "Greeter" in symbols
    assert len(chunks) == 3  # leftover import + function + class