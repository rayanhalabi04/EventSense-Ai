from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.models.message import Message


class ConversationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, conversation_id: UUID) -> Conversation | None:
        return await self.session.get(Conversation, conversation_id)

    async def list(self, tenant_id: UUID) -> list[Conversation]:
        result = await self.session.execute(
            select(Conversation)
            .where(Conversation.tenant_id == tenant_id)
            .order_by(Conversation.created_at.desc())
        )
        return list(result.scalars().all())

    async def find_latest_by_client(
        self,
        tenant_id: UUID,
        *,
        client_name: str,
        client_contact: str | None,
    ) -> Conversation | None:
        query = (
            select(Conversation)
            .where(
                Conversation.tenant_id == tenant_id,
                func.lower(Conversation.client_name) == client_name.lower(),
            )
            .order_by(Conversation.created_at.desc())
            .limit(1)
        )
        if client_contact is None:
            query = query.where(Conversation.client_contact.is_(None))
        else:
            query = query.where(Conversation.client_contact == client_contact)

        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def add(self, conversation: Conversation) -> Conversation:
        self.session.add(conversation)
        await self.session.flush()
        return conversation

    async def list_with_message_counts(self, tenant_id: UUID) -> list[tuple[Conversation, int]]:
        message_counts = (
            select(Message.conversation_id, func.count(Message.id).label("message_count"))
            .where(Message.tenant_id == tenant_id)
            .group_by(Message.conversation_id)
            .subquery()
        )
        result = await self.session.execute(
            select(Conversation, func.coalesce(message_counts.c.message_count, 0))
            .outerjoin(message_counts, message_counts.c.conversation_id == Conversation.id)
            .where(Conversation.tenant_id == tenant_id)
            .order_by(Conversation.updated_at.desc())
        )
        return [(conversation, count) for conversation, count in result.all()]
