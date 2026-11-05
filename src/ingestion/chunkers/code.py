import tree_sitter_java
import tree_sitter_javascript
import tree_sitter_python
import tree_sitter_typescript
from tree_sitter import Language, Parser

from src.config import get_settings
from src.ingestion.chunkers.base import BaseChunker
from src.ingestion.models import Chunk, Document

# file extension -> (language, node types that count as "top-level definitions")
LANGUAGES: dict[str, tuple[Language, set[str]]] = {
    ".py": (
        Language(tree_sitter_python.language()),
        {"function_definition", "class_definition", "decorated_definition"},
    ),
    ".js": (
        Language(tree_sitter_javascript.language()),
        {"function_declaration", "class_declaration", "method_definition",
         "arrow_function", "export_statement"},
    ),
}

JS_DEFINITIONS = LANGUAGES[".js"][1] | {
    "lexical_declaration",
    "variable_declaration",
}

LANGUAGES[".js"] = (
    Language(tree_sitter_javascript.language()),
    JS_DEFINITIONS,
)

LANGUAGES.update({
    ".jsx": (
        Language(tree_sitter_javascript.language()),
        JS_DEFINITIONS,
    ),
    ".ts": (
        Language(tree_sitter_typescript.language_typescript()),
        JS_DEFINITIONS | {
            "interface_declaration",
            "type_alias_declaration",
            "enum_declaration",
            "abstract_class_declaration",
        },
    ),
    ".tsx": (
        Language(tree_sitter_typescript.language_tsx()),
        JS_DEFINITIONS | {
            "interface_declaration",
            "type_alias_declaration",
            "enum_declaration",
            "abstract_class_declaration",
        },
    ),
    ".java": (
        Language(tree_sitter_java.language()),
        {
            "class_declaration",
            "interface_declaration",
            "enum_declaration",
            "record_declaration",
            "annotation_type_declaration",
        },
    ),
})


class CodeChunker(BaseChunker):
    """AST-aware chunker: splits on function/class boundaries via tree-sitter."""

    def __init__(self):
        self.max_lines = get_settings().max_code_chunk_lines
        self._parsers: dict[str, Parser] = {}

    def chunk(self, document: Document) -> list[Chunk]:
        ext = document.metadata.get("extension", "").lower()
        lang = LANGUAGES.get(ext)
        if lang is None:
            return self._fallback_lines(document)

        language, def_types = lang
        parser = self._parsers.get(ext)
        if parser is None:
            parser = self._parsers[ext] = Parser(language)
        source = document.content.encode("utf-8")
        tree = parser.parse(source)
        lines = document.content.splitlines()

        if tree.root_node.has_error:
            return self._fallback_lines(document)

        chunks: list[Chunk] = []
        covered_lines: set[int] = set()

        for node in tree.root_node.children:
            if node.type in def_types:
                text = source[node.start_byte:node.end_byte].decode("utf-8")
                symbol = self._node_name(node, source)
                for piece in self._subdivide(text):
                    chunks.append(Chunk(
                        content=piece,
                        document=document,
                        chunk_index=len(chunks),
                        metadata={**document.metadata, "symbol": symbol},
                    ))
                total = len(lines)
                covered_lines.update(range(
                    min(node.start_point.row, total),
                    min(node.end_point.row + 1, total),
                ))

        # code outside defs (imports, constants, module-level statements)
        leftovers = [
            line for i, line in enumerate(lines)
            if i not in covered_lines
        ]
        if any(l.strip() for l in leftovers):
            chunks.insert(0, Chunk(
                content="\n".join(leftovers),
                document=document,
                chunk_index=0,
                metadata={**document.metadata, "symbol": "<module>"},
            ))
            for i, c in enumerate(chunks):
                c.chunk_index = i  # reindex after insert

        return chunks

    def _node_name(self, node, source: bytes) -> str:
        name_node = node.child_by_field_name("name")
        if name_node is not None:
            return source[name_node.start_byte:name_node.end_byte].decode("utf-8")

        wrapper_types = {
            "decorated_definition",
            "export_statement",
            "lexical_declaration",
            "variable_declaration",
        }
        if node.type in wrapper_types:
            for child in node.named_children:
                name = self._node_name(child, source)
                if name != "<anonymous>":
                    return name

        return "<anonymous>"

    def _subdivide(self, text: str) -> list[str]:
        """Split overlong definitions at max_lines boundaries."""
        lines = text.splitlines()
        return ["\n".join(lines[i:i + self.max_lines])
                for i in range(0, len(lines), self.max_lines)] or [text]

    def _fallback_lines(self, document: Document) -> list[Chunk]:
        return [Chunk(content=p, document=document, chunk_index=i,
                      metadata={**document.metadata})
                for i, p in enumerate(self._subdivide(document.content))]