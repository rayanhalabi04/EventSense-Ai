from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.message import MessageDirection, MessageStatus


class MessageCreate(BaseModel):
    body: str
    direction: MessageDirection = MessageDirection.outbound

    model_config = ConfigDict(extra="ignore")


class MessageRead(BaseModel):
    id: UUID
    tenant_id: UUID
    conversation_id: UUID
    direction: MessageDirection
    status: MessageStatus
    body: str
    source: str | None
    intent_label: str | None = None
    intent_confidence: float | None = None
    classified_at: datetime | None = None
    risk_level: str | None = None
    risk_flags: list[str] | None = None
    risk_reason: str | None = None
    risk_detected_at: datetime | None = None
    sender_user_id: UUID | None
    sent_at: datetime

    model_config = ConfigDict(from_attributes=True)
