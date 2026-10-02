from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class Document(BaseModel):
    content: str
    source_type: str          # "markdown" | "code" | "incident"
    source_path: str          # file path or URL
    metadata: dict[str, Any] = {}


class Chunk(BaseModel):
    content: str
    document: Document
    chunk_index: int           # position within the document
    metadata: dict[str, Any] = {}