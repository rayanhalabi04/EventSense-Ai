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

    async def add(self, message: Message) -> Message:
        self.session.add(message)
        await self.session.flush()
        return message
