from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    """Body for POST /api/query."""
    query: str = Field(min_length=1, examples=["why was my pod evicted?"])
    session_id: str = Field(default="default", examples=["demo-session"])
    source_type: str | None = Field(default=None, examples=["incident"])
    repository: str | None = None
    language: str | None = None
    severity: str | None = None

    model_config = {
        "json_schema_extra": {
            "examples": [{"query": "auth broken after deploy", "session_id": "s1", "source_type": "incident"}]
        }
    }