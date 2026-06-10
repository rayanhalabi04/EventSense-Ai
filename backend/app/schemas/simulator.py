from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class SimulatorMessageRequest(BaseModel):
    client_name: str | None = None
    client_contact: str | None = None
    body: str
    conversation_id: UUID | None = None

    model_config = ConfigDict(extra="ignore")

    @field_validator("body")
    @classmethod
    def validate_body(cls, value: str) -> str:
        body = value.strip()
        if not body:
            raise ValueError("Message body cannot be empty or whitespace only")
        if len(body) > 4000:
            raise ValueError("Message body cannot exceed 4000 characters")
        return body

    @model_validator(mode="after")
    def validate_conversation_or_client_name(self) -> "SimulatorMessageRequest":
        if self.client_name is not None:
            self.client_name = self.client_name.strip()
        if self.conversation_id is None and not self.client_name:
            raise ValueError("Client name cannot be empty")
        return self


class SimulatorMessageResponse(BaseModel):
    message_id: UUID
    conversation_id: UUID
    is_new_conversation: bool
    conversation_status: str
    tenant_id: UUID
    intent_label: str | None = None
    intent_confidence: float | None = None
    classified_at: datetime | None = None
    risk_level: str | None = None
    risk_flags: list[str] | None = None
    risk_reason: str | None = None
    risk_detected_at: datetime | None = None


class SimulatorConversationItem(BaseModel):
    id: UUID
    client_name: str
    client_contact: str | None
    status: str
    message_count: int
    updated_at: datetime


class SimulatorConversationsResponse(BaseModel):
    items: list[SimulatorConversationItem]
    total: int


SimulatedWhatsAppMessageCreate = SimulatorMessageRequest
SimulatedWhatsAppMessageRead = SimulatorMessageResponse
