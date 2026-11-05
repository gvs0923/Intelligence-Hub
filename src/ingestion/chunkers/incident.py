from src.ingestion.chunkers.base import BaseChunker
from src.ingestion.chunkers.text import TextChunker
from src.ingestion.incident_models import IncidentRecord
from src.ingestion.models import Chunk, Document


class IncidentChunker(BaseChunker):
    def __init__(self):
        self._text_chunker = TextChunker()

    def chunk(self, document: Document) -> list[Chunk]:
        incident = IncidentRecord.model_validate_json(document.content)
        chunks = []

        for field in ("description", "root_cause", "resolution"):
            text = getattr(incident, field)
            if not text:
                continue

            section = Document(
                content=text,
                source_type=document.source_type,
                source_path=document.source_path,
                metadata={**document.metadata, "incident_field": field},
            )

            for part in self._text_chunker.chunk(section):
                chunks.append(
                    Chunk(
                        content=(
                            f"Incident: {incident.title}\n"
                            f"Field: {field}\n\n"
                            f"{part.content}"
                        ),
                        document=document,
                        chunk_index=len(chunks),
                        metadata=part.metadata,
                    )
                )

        return chunks