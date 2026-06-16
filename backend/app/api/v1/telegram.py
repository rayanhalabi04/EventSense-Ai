from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_async_session
from app.core.tenant_context import TenantContext, require_role
from app.models.user import UserRole
from app.schemas.telegram import TelegramReplyRequest, TelegramReplyResponse
from app.services.telegram_service import (
    TelegramApiError,
    TelegramService,
    parse_telegram_update,
)


router = APIRouter()


@router.post("/integrations/telegram/webhook/{tenant_slug}")
async def receive_telegram_webhook(
    tenant_slug: str,
    update: dict,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, object]:
    if (
        not settings.telegram_webhook_secret
        or x_telegram_bot_api_secret_token != settings.telegram_webhook_secret
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    if not settings.telegram_enabled:
        return {"ok": True, "ignored": True, "reason": "telegram_disabled"}

    parsed = parse_telegram_update(update)
    if parsed is None:
        return {"ok": True, "ignored": True}

    conversation, message, is_new_conversation = await TelegramService.ingest_webhook_message(
        session,
        tenant_slug=tenant_slug,
        parsed=parsed,
    )
    return {
        "ok": True,
        "ignored": False,
        "conversation_id": str(conversation.id),
        "message_id": str(message.id),
        "is_new_conversation": is_new_conversation,
    }


@router.post(
    "/conversations/{conversation_id}/send-telegram-reply",
    response_model=TelegramReplyResponse,
    status_code=status.HTTP_201_CREATED,
)
async def send_telegram_reply(
    conversation_id: UUID,
    payload: TelegramReplyRequest,
    ctx: TenantContext = Depends(require_role(UserRole.staff, UserRole.manager)),
    session: AsyncSession = Depends(get_async_session),
) -> TelegramReplyResponse:
    try:
        message = await TelegramService().send_staff_reply(
            session,
            conversation_id=conversation_id,
            text=payload.text,
            ctx=ctx,
            suggested_reply_id=payload.suggested_reply_id,
        )
    except TelegramApiError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    return TelegramReplyResponse(
        ok=True,
        message_id=str(message.id),
        telegram_message_id=message.external_message_id,
        conversation_id=str(conversation_id),
    )
