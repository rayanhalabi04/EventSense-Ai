from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.conversation import ConversationStatus
from app.models.message import MessageDirection


class InboxFilters(BaseModel):
    unread_only: bool = False
    status: ConversationStatus | None = None
    search: str | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)

    @field_validator("search")
    @classmethod
    def normalize_search(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class InboxItemResponse(BaseModel):
    conversation_id: UUID
    latest_message_id: UUID | None = None
    client_name: str
    client_contact: str | None
    latest_message_preview: str | None
    latest_message_at: datetime | None
    latest_message_direction: MessageDirection | None
    intent_label: str | None = None
    intent_confidence: float | None = None
    classified_at: datetime | None = None
    risk_level: str | None = None
    risk_flags: list[str] | None = None
    risk_reason: str | None = None
    risk_detected_at: datetime | None = None
    unread_count: int
    has_unread: bool
    conversation_status: ConversationStatus
    updated_at: datetime


class InboxResponse(BaseModel):
    items: list[InboxItemResponse]
    total: int
    total_unread: int
    page: int
    page_size: int
    total_pages: int


class InboxSummaryResponse(BaseModel):
    total_open: int
    unread_or_new: int
    high_risk: int = 0


class InboxMessageRow(BaseModel):
    conversation_id: UUID
    latest_message_id: UUID
    client_name: str
    client_contact: str | None
    message_preview: str
    latest_message_body: str
    latest_message_at: datetime
    status: ConversationStatus
    source: str | None
    direction: MessageDirection
    intent_label: str | None = None
    intent_confidence: float | None = None
    classified_at: datetime | None = None
    risk_level: str | None = None
    risk_flags: list[str] | None = None
    risk_reason: str | None = None
    risk_detected_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
