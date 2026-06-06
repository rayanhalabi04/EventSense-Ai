from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.conversation import ConversationStatus


class ConversationCreate(BaseModel):
    client_name: str
    client_contact: str | None = None

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
