from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.models.conversation import ConversationStatus
from app.models.message import MessageDirection


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
    intent_label: None = None
    risk_level: None = None
