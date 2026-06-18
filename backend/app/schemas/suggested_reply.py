from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.suggested_reply import SuggestedReplyStatus


class SuggestedReplySource(BaseModel):
    document_id: UUID
    document_title: str
    document_type: str
    content: str
    score: float

    model_config = ConfigDict(extra="ignore")


class SuggestedReplyGenerateRequest(BaseModel):
    """Optional body for the generate endpoint.

    tenant_id is intentionally absent — the tenant is always taken from the
    authenticated context, never from the request body.
    """

    message_id: UUID | None = None

    model_config = ConfigDict(extra="ignore")


class SuggestedReplyUpdate(BaseModel):
    status: SuggestedReplyStatus | None = None
    suggested_text: str | None = None

    model_config = ConfigDict(extra="ignore")

    @field_validator("suggested_text")
    @classmethod
    def validate_suggested_text(cls, value: str | None) -> str | None:
        if value is None:
            return value
        text = value.strip()
        if not text:
            raise ValueError("suggested_text cannot be empty or whitespace only")
        if len(text) > 4000:
            raise ValueError("suggested_text cannot exceed 4000 characters")
        return text


class SuggestedReplyRead(BaseModel):
    id: UUID
    tenant_id: UUID
    conversation_id: UUID
    message_id: UUID | None
    suggested_text: str
    status: SuggestedReplyStatus
    source_document_ids: list[str]
    rag_sources: list[dict[str, object]]
    answer_supported: bool
    refusal_reason: str | None
    generation_method: str
    small_talk_category: str | None = None
    auto_sent_at: datetime | None = None
    sent_channel: str | None = None
    created_by_user_id: UUID | None
    approved_by_user_id: UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
