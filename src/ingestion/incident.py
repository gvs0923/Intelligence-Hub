import csv
import json
from pathlib import Path

from src.ingestion.base import BaseIngester
from src.ingestion.incident_models import IncidentRecord
from src.ingestion.models import Document


class IncidentIngester(BaseIngester):
    def ingest(self, source: str) -> list[Document]:
        path = Path(source).expanduser().resolve()

        if not path.is_file():
            raise ValueError(f"Not a file: {path}")

        if path.suffix.lower() == ".json":
            with path.open(encoding="utf-8-sig") as handle:
                data = json.load(handle)
            records = data if isinstance(data, list) else [data]
        elif path.suffix.lower() == ".csv":
            with path.open(encoding="utf-8-sig", newline="") as handle:
                records = list(csv.DictReader(handle))
        else:
            raise ValueError(f"Unsupported incident file type: {path.suffix}")

        documents = []
        identities = set()

        for index, raw in enumerate(records):
            if not isinstance(raw, dict):
                raise TypeError(f"Incident record {index + 1} must be an object")

            incident = IncidentRecord.model_validate(raw)
            identity = f"id:{incident.id}" if incident.id else f"row:{index}"

            if identity in identities:
                raise ValueError(f"Duplicate incident identity: {identity}")
            identities.add(identity)

            payload = incident.model_dump(mode="json")
            documents.append(
                Document(
                    content=json.dumps(payload, sort_keys=True, ensure_ascii=False),
                    source_type="incident",
                    source_path=f"{path}::{identity}",
                    metadata={
                        "file_path": str(path),
                        "incident_id": incident.id,
                        "title": incident.title,
                        "severity": incident.severity,
                        "timestamp": payload["timestamp"],
                    },
                )
            )

        return documents