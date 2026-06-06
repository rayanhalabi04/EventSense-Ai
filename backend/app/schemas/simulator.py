from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.schemas.conversation import ConversationRead
from app.schemas.message import MessageRead


class SimulatedWhatsAppMessageCreate(BaseModel):
    conversation_id: UUID | None = None
    client_name: str | None = None
    client_contact: str | None = None
    body: str

    model_config = ConfigDict(extra="ignore")


class SimulatedWhatsAppMessageRead(BaseModel):
    conversation: ConversationRead
    message: MessageRead
