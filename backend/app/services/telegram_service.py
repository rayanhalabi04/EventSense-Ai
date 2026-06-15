from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import httpx
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.tenant_context import TenantContext
from app.models.conversation import Conversation, ConversationStatus
from app.models.message import Message, MessageDirection
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.message_repository import MessageRepository
from app.repositories.tenant_repository import TenantRepository
from app.services.audit_log_service import (
    AUDIT_EVENT_TELEGRAM_MESSAGE_RECEIVED,
    AUDIT_EVENT_TELEGRAM_REPLY_SENT,
    AUDIT_EVENT_TENANT_CROSS_TENANT_ACCESS_BLOCKED,
    AuditLogService,
)
from app.services.conversation_memory_service import ConversationMemoryService
from app.services.simulator_service import SimulatorService


TELEGRAM_SOURCE = "telegram"


@dataclass(frozen=True)
class ParsedTelegramMessage:
    text: str
    chat_id: str
    from_id: str | None
    username: str | None
    first_name: str | None
    message_id: str

    @property
    def client_name(self) -> str:
        return self.username or self.first_name or self.chat_id


def parse_telegram_update(update: dict[str, Any]) -> ParsedTelegramMessage | None:
    message = update.get("message")
    if not isinstance(message, dict):
        return None
    text = message.get("text")
    if not isinstance(text, str) or not text.strip():
        return None
    chat = message.get("chat")
    if not isinstance(chat, dict) or chat.get("id") is None:
        return None
    sender = message.get("from")
    if not isinstance(sender, dict):
        sender = {}
    message_id = message.get("message_id")
    if message_id is None:
        return None
    return ParsedTelegramMessage(
        text=text.strip(),
        chat_id=str(chat["id"]),
        from_id=str(sender["id"]) if sender.get("id") is not None else None,
        username=sender.get("username") if isinstance(sender.get("username"), str) else None,
        first_name=sender.get("first_name") if isinstance(sender.get("first_name"), str) else None,
        message_id=str(message_id),
    )


class TelegramApiError(RuntimeError):
    pass


class TelegramService:
    def __init__(
        self,
        *,
        bot_token: str | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.bot_token = bot_token if bot_token is not None else settings.telegram_bot_token
        self.timeout_seconds = timeout_seconds

    async def send_message(self, chat_id: str, text: str) -> dict[str, Any]:
        if not self.bot_token:
            raise TelegramApiError("Telegram bot token is not configured")
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {"chat_id": chat_id, "text": text}
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise TelegramApiError("Telegram sendMessage request failed") from exc
        if not data.get("ok"):
            description = data.get("description") if isinstance(data, dict) else None
            raise TelegramApiError(str(description or "Telegram API rejected sendMessage"))
        return data

    @staticmethod
    async def ingest_webhook_message(
        session: AsyncSession,
        *,
        tenant_slug: str,
        parsed: ParsedTelegramMessage,
    ) -> tuple[Conversation, Message, bool]:
        tenant = await TenantRepository(session).get_by_slug(tenant_slug)
        if tenant is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="tenant not found")

        conversations = ConversationRepository(session)
        conversation = await conversations.find_by_external_conversation_id(
            tenant.id,
            source=TELEGRAM_SOURCE,
            external_conversation_id=parsed.chat_id,
        )
        is_new_conversation = conversation is None
        if conversation is None:
            conversation = Conversation(
                tenant_id=tenant.id,
                client_name=parsed.client_name,
                client_contact=parsed.chat_id,
                source=TELEGRAM_SOURCE,
                external_conversation_id=parsed.chat_id,
            )
            await conversations.add(conversation)
        else:
            if conversation.status == ConversationStatus.closed:
                conversation.status = ConversationStatus.open
            conversation.client_name = parsed.client_name
            conversation.client_contact = parsed.chat_id

        message = await SimulatorService.create_inbound_message(
            session=session,
            tenant_id=tenant.id,
            actor_user_id=None,
            conversation=conversation,
            body=parsed.text,
            source=TELEGRAM_SOURCE,
            external_message_id=parsed.message_id,
        )
        AuditLogService.record(
            session,
            tenant_id=tenant.id,
            actor_user_id=None,
            event_type=AUDIT_EVENT_TELEGRAM_MESSAGE_RECEIVED,
            resource_type="message",
            resource_id=message.id,
            details={
                "conversation_id": conversation.id,
                "chat_id": parsed.chat_id,
                "telegram_user_id": parsed.from_id,
                "telegram_username": parsed.username,
                "is_new_conversation": is_new_conversation,
            },
        )
        await session.commit()
        await session.refresh(conversation)
        await session.refresh(message)
        await ConversationMemoryService().store_inbound_message(
            tenant_id=tenant.id,
            message=message,
        )
        from app.services.telegram_auto_reply_service import TelegramAutoReplyService

        await TelegramAutoReplyService().maybe_auto_reply(
            session,
            conversation=conversation,
            message=message,
        )
        return conversation, message, is_new_conversation

    async def send_staff_reply(
        self,
        session: AsyncSession,
        *,
        conversation_id: UUID,
        text: str,
        ctx: TenantContext,
    ) -> Message:
        conversation = await ConversationRepository(session).get(conversation_id)
        if conversation is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="conversation not found")
        if conversation.tenant_id != ctx.tenant_id:
            AuditLogService.record(
                session,
                tenant_id=ctx.tenant_id,
                actor_user_id=ctx.user_id,
                event_type=AUDIT_EVENT_TENANT_CROSS_TENANT_ACCESS_BLOCKED,
                resource_type="conversation",
                resource_id=conversation.id,
                details={"requested_conversation_tenant_id": conversation.tenant_id},
            )
            await session.commit()
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
        if conversation.source != TELEGRAM_SOURCE or not conversation.external_conversation_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="conversation is not a Telegram conversation",
            )

        telegram_response = await self.send_message(conversation.external_conversation_id, text)
        telegram_message_id = _sent_message_id(telegram_response)
        now = datetime.now(timezone.utc)
        conversation.updated_at = now
        message = Message(
            tenant_id=ctx.tenant_id,
            conversation_id=conversation.id,
            direction=MessageDirection.outbound,
            body=text,
            source=TELEGRAM_SOURCE,
            external_message_id=telegram_message_id,
            sender_user_id=ctx.user_id,
            sent_at=now,
        )
        await MessageRepository(session).add(message)
        AuditLogService.record(
            session,
            tenant_id=ctx.tenant_id,
            actor_user_id=ctx.user_id,
            event_type=AUDIT_EVENT_TELEGRAM_REPLY_SENT,
            resource_type="message",
            resource_id=message.id,
            details={
                "conversation_id": conversation.id,
                "chat_id": conversation.external_conversation_id,
                "telegram_message_id": telegram_message_id,
            },
        )
        await session.commit()
        await session.refresh(message)
        return message


def _sent_message_id(response: dict[str, Any]) -> str | None:
    result = response.get("result")
    if isinstance(result, dict) and result.get("message_id") is not None:
        return str(result["message_id"])
    return None
