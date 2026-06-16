from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.escalation import EscalationStatus


class EscalationCreate(BaseModel):
    conversation_id: UUID
    message_id: UUID | None = None
    assigned_manager_user_id: UUID | None = None
    ai_summary: str | None = None
    suggested_next_step: str | None = None
    status: EscalationStatus = EscalationStatus.open

    model_config = ConfigDict(extra="ignore")


class EscalationUpdate(BaseModel):
    assigned_manager_user_id: UUID | None = None
    ai_summary: str | None = None
    suggested_next_step: str | None = None
    status: EscalationStatus | None = None

    model_config = ConfigDict(extra="ignore")


class EscalationRead(BaseModel):
    id: UUID
    tenant_id: UUID
    conversation_id: UUID
    message_id: UUID | None
    # Nullable: automated inbound processing (e.g. the Telegram pipeline) creates
    # system-owned escalations with no authenticated user. The DB column is
    # nullable to match, so this serializer must accept None or it raises a
    # ValidationError (HTTP 500) when reading such a conversation's detail.
    created_by_user_id: UUID | None
    assigned_manager_user_id: UUID | None
    intent_label: str | None
    risk_level: str | None
    risk_reason: str | None
    ai_summary: str | None
    suggested_next_step: str | None
    status: EscalationStatus
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None

    model_config = ConfigDict(from_attributes=True)
