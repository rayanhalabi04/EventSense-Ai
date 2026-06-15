from pydantic import BaseModel, ConfigDict, Field, field_validator


class TelegramReplyRequest(BaseModel):
    text: str = Field(..., max_length=4096)

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
