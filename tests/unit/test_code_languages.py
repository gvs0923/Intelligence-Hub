import pytest

from src.ingestion.chunkers.code import CodeChunker
from src.ingestion.models import Document


@pytest.mark.parametrize(
    ("extension", "content", "symbol"),
    [
        (
            ".py",
            "def greet():\n    return 'hello'\n",
            "greet",
        ),
        (
            ".js",
            "function greet() { return 'hello'; }\n",
            "greet",
        ),
        (
            ".jsx",
            "const Button = () => <button>Save</button>;\n",
            "Button",
        ),
        (
            ".ts",
            "interface User { name: string; }\n",
            "User",
        ),
        (
            ".tsx",
            "const Button = (): JSX.Element => <button>Save</button>;\n",
            "Button",
        ),
        (
            ".java",
            "class User { String name; }\n",
            "User",
        ),
    ],
)
def test_languages_use_ast_chunks(extension, content, symbol):
    document = Document(
        content=content,
        source_type="code",
        source_path=f"example{extension}",
        metadata={"extension": extension},
    )

    chunks = CodeChunker().chunk(document)

    assert any(chunk.metadata.get("symbol") == symbol for chunk in chunks)


def test_invalid_python_falls_back_to_lines():
    document = Document(
        content="def broken(\n",
        source_type="code",
        source_path="broken.py",
        metadata={"extension": ".py"},
    )

    chunks = CodeChunker().chunk(document)

    assert chunks
    assert chunks[0].content == "def broken("
    assert "symbol" not in chunks[0].metadata