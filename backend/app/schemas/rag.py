from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.document import DocumentType


class RagQueryRequest(BaseModel):
    query: str
    top_k: int = Field(default=5, ge=1, le=20)
    document_type_filter: DocumentType | None = None

    model_config = ConfigDict(extra="ignore")

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value


class RagSourceRead(BaseModel):
    document_id: UUID
    document_title: str
    document_type: str
    content: str
    score: float
    chunk_index: int
    metadata: dict[str, object]


class RagQueryResponse(BaseModel):
    query: str
    answer_supported: bool
    sources: list[RagSourceRead]
    refusal_reason: str | None = None
