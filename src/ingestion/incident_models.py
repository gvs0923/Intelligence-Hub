from datetime import datetime

from pydantic import BaseModel, field_validator, model_validator


class IncidentRecord(BaseModel):
    id: str | None = None
    title: str
    description: str = ""
    root_cause: str = ""
    resolution: str = ""
    severity: str | None = None
    timestamp: datetime | None = None

    @field_validator(
        "id",
        "title",
        "description",
        "root_cause",
        "resolution",
        "severity",
        mode="before",
    )
    @classmethod
    def strip_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("id", "severity", "timestamp", mode="before")
    @classmethod
    def empty_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("title")
    @classmethod
    def require_title(cls, value: str) -> str:
        if not value:
            raise ValueError("Incident title must not be empty")
        return value

    @model_validator(mode="after")
    def require_incident_content(self) -> "IncidentRecord":
        if not any((self.description, self.root_cause, self.resolution)):
            raise ValueError(
                "Incident must include description, root_cause, or resolution"
            )
        return self