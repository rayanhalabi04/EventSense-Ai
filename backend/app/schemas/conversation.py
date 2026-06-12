from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.conversation import ConversationStatus
from app.models.message import MessageDirection, MessageStatus
from app.schemas.escalation import EscalationRead
from app.schemas.suggested_reply import SuggestedReplyRead
from app.schemas.task import TaskRead


class ConversationCreate(BaseModel):
    client_name: str
    client_contact: str | None = None

    model_config = ConfigDict(extra="ignore")


class ConversationUpdate(BaseModel):
    status: ConversationStatus

    model_config = ConfigDict(extra="ignore")


class ConversationRead(BaseModel):
    id: UUID
    tenant_id: UUID
    client_name: str
    client_contact: str | None
    status: ConversationStatus
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ConversationDetailMessage(BaseModel):
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


class ConversationDetailAuditEvent(BaseModel):
    id: UUID
    event_type: str
    actor_user_id: UUID | None
    resource_type: str | None
    resource_id: str | None
    details: dict[str, object]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ConversationDetailResponse(BaseModel):
    conversation_id: UUID
    client_name: str
    client_contact: str | None
    conversation_status: ConversationStatus
    created_at: datetime
    updated_at: datetime
    messages: list[ConversationDetailMessage]
    latest_inbound_message: ConversationDetailMessage | None
    latest_intent_label: str | None = None
    latest_intent_confidence: float | None = None
    latest_classified_at: datetime | None = None
    latest_risk_level: str | None = None
    latest_risk_flags: list[str] | None = None
    latest_risk_reason: str | None = None
    latest_risk_detected_at: datetime | None = None
    audit_timeline: list[ConversationDetailAuditEvent]
    suggested_reply: SuggestedReplyRead | None = None
    rag_sources: list[dict[str, object]]
    tasks: list[TaskRead]
    escalations: list[EscalationRead]
