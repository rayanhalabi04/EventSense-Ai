from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message import Message, MessageDirection


class MessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, message_id: UUID) -> Message | None:
        return await self.session.get(Message, message_id)

    async def list_for_conversation(self, tenant_id: UUID, conversation_id: UUID) -> list[Message]:
        result = await self.session.execute(
            select(Message)
            .where(Message.tenant_id == tenant_id, Message.conversation_id == conversation_id)
            .order_by(Message.sent_at.asc(), Message.id.asc())
        )
        return list(result.scalars().all())

    async def latest_inbound_for_conversation(
        self,
        tenant_id: UUID,
        conversation_id: UUID,
    ) -> Message | None:
        result = await self.session.execute(
            select(Message)
            .where(
                Message.tenant_id == tenant_id,
                Message.conversation_id == conversation_id,
                Message.direction == MessageDirection.inbound,
            )
            .order_by(Message.sent_at.desc(), Message.id.desc())
            .limit(1)
        )
        return result.scalars().first()

    async def latest_outbound_for_conversation(
        self,
        tenant_id: UUID,
        conversation_id: UUID,
        *,
        source: str | None = None,
    ) -> Message | None:
        """Return the most recent outbound message (optionally filtered by source).

        Used by the Telegram staff-reply path to stay idempotent: if a suggested
        reply was already sent, a second click returns the existing outbound
        message instead of sending again.
        """
        query = select(Message).where(
            Message.tenant_id == tenant_id,
            Message.conversation_id == conversation_id,
            Message.direction == MessageDirection.outbound,
        )
        if source is not None:
            query = query.where(Message.source == source)
        result = await self.session.execute(
            query.order_by(Message.sent_at.desc(), Message.id.desc()).limit(1)
        )
        return result.scalars().first()

    async def find_inbound_by_external_id(
        self,
        tenant_id: UUID,
        *,
        source: str,
        external_message_id: str,
    ) -> Message | None:
        """Return an already-stored inbound message for an external provider id.

        Used to make webhook ingestion idempotent: if a provider retries the same
        update we must not create a duplicate message (and therefore no duplicate
        reply, escalation, or auto-send).
        """
        result = await self.session.execute(
            select(Message)
            .where(
                Message.tenant_id == tenant_id,
                Message.source == source,
                Message.direction == MessageDirection.inbound,
                Message.external_message_id == external_message_id,
            )
            .order_by(Message.sent_at.asc(), Message.id.asc())
            .limit(1)
        )
        return result.scalars().first()

    async def add(self, message: Message) -> Message:
        self.session.add(message)
        await self.session.flush()
        return message
