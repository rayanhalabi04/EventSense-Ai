from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TelegramReplyRequest(BaseModel):
    text: str = Field(..., max_length=4096)
    # Optional: when the staff member is sending an AI suggested reply, the
    # frontend passes its id so the backend can mark it sent (status=approved,
    # sent_channel=telegram) and stay idempotent if the button is clicked twice.
    suggested_reply_id: UUID | None = None

    model_config = ConfigDict(extra="ignore")

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("Reply text cannot be empty")
        return text


class TelegramReplyResponse(BaseModel):
    ok: bool
    message_id: str
    telegram_message_id: str | None = None
    conversation_id: str
