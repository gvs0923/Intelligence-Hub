from src.ingestion.code import CodeIngester
from src.ingestion.markdown import MarkdownIngester


def test_markdown_ingester_reads_md_files(tmp_path):
    (tmp_path / "a.md").write_text("# Hello")
    (tmp_path / "b.txt").write_text("ignored")  # wrong extension

    docs = MarkdownIngester().ingest(str(tmp_path))

    assert len(docs) == 1
    assert docs[0].content == "# Hello"
    assert docs[0].source_type == "markdown"


def test_code_ingester_skips_junk_dirs(tmp_path):
    (tmp_path / "real.py").write_text("x = 1")
    junk = tmp_path / "__pycache__"
    junk.mkdir()
    (junk / "cached.py").write_text("y = 2")

    docs = CodeIngester().ingest(str(tmp_path))

    assert len(docs) == 1
    assert docs[0].source_path.endswith("real.py")