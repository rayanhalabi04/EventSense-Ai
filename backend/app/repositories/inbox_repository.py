from __future__ import annotations

from uuid import UUID

from sqlalchemy import exists, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.conversation import Conversation, ConversationStatus
from app.models.message import Message, MessageDirection, MessageStatus
from app.schemas.inbox import InboxFilters


class InboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def _latest_message_id_subquery(tenant_id: UUID):
        latest_message = aliased(Message)
        return (
            select(latest_message.id)
            .where(
                latest_message.conversation_id == Conversation.id,
                latest_message.tenant_id == tenant_id,
            )
            .order_by(latest_message.sent_at.desc(), latest_message.id.desc())
            .limit(1)
            .correlate(Conversation)
            .scalar_subquery()
        )

    @staticmethod
    def _unread_count_subquery(tenant_id: UUID):
        unread_message = aliased(Message)
        return (
            select(func.count(unread_message.id))
            .where(
                unread_message.conversation_id == Conversation.id,
                unread_message.tenant_id == tenant_id,
                unread_message.status == MessageStatus.unread,
            )
            .correlate(Conversation)
            .scalar_subquery()
        )

    @classmethod
    def _base_inbox_statement(cls, tenant_id: UUID, filters: InboxFilters):
        latest_message_id = cls._latest_message_id_subquery(tenant_id)
        unread_count = cls._unread_count_subquery(tenant_id)
        latest_message = aliased(Message)

        stmt = (
            select(
                Conversation.id.label("conversation_id"),
                Conversation.client_name,
                Conversation.client_contact,
                Conversation.status.label("conversation_status"),
                Conversation.updated_at,
                latest_message.id.label("latest_message_id"),
                latest_message.body.label("latest_message_body"),
                latest_message.sent_at.label("latest_message_at"),
                latest_message.direction.label("latest_message_direction"),
                latest_message.intent_label,
                latest_message.intent_confidence,
                latest_message.classified_at,
                latest_message.risk_level,
                latest_message.risk_flags,
                latest_message.risk_reason,
                latest_message.risk_detected_at,
                unread_count.label("unread_count"),
            )
            .outerjoin(latest_message, latest_message.id == latest_message_id)
            .where(Conversation.tenant_id == tenant_id)
        )

        if filters.status is not None:
            stmt = stmt.where(Conversation.status == filters.status)
        if filters.unread_only:
            stmt = stmt.where(unread_count > 0)
        if filters.search is not None and len(filters.search) >= 2:
            pattern = f"%{filters.search}%"
            search_message = aliased(Message)
            message_match = exists(
                select(literal(1)).where(
                    search_message.conversation_id == Conversation.id,
                    search_message.tenant_id == tenant_id,
                    search_message.body.ilike(pattern),
                )
            ).correlate(Conversation)
            stmt = stmt.where(
                or_(
                    Conversation.client_name.ilike(pattern),
                    Conversation.client_contact.ilike(pattern),
                    message_match,
                )
            )

        return stmt

    async def count_inbox_items(self, tenant_id: UUID, filters: InboxFilters) -> int:
        base_stmt = self._base_inbox_statement(tenant_id, filters)
        return (
            await self.session.execute(select(func.count()).select_from(base_stmt.subquery()))
        ).scalar_one()

    async def list_inbox_rows(self, tenant_id: UUID, filters: InboxFilters) -> list[object]:
        base_stmt = self._base_inbox_statement(tenant_id, filters)
        result = await self.session.execute(
            base_stmt.order_by(Conversation.updated_at.desc(), Conversation.id.desc())
            .offset((filters.page - 1) * filters.page_size)
            .limit(filters.page_size)
        )
        return list(result.all())

    async def count_open_conversations(self, tenant_id: UUID) -> int:
        return (
            await self.session.execute(
                select(func.count(Conversation.id)).where(
                    Conversation.tenant_id == tenant_id,
                    Conversation.status == ConversationStatus.open,
                )
            )
        ).scalar_one()

    async def count_unread_conversations(self, tenant_id: UUID) -> int:
        return (
            await self.session.execute(
                select(func.count(func.distinct(Message.conversation_id))).where(
                    Message.tenant_id == tenant_id,
                    Message.status == MessageStatus.unread,
                )
            )
        ).scalar_one()

    async def count_high_risk_conversations(self, tenant_id: UUID) -> int:
        return (
            await self.session.execute(
                select(func.count(func.distinct(Message.conversation_id))).where(
                    Message.tenant_id == tenant_id,
                    Message.risk_level == "high",
                )
            )
        ).scalar_one()

    async def list_latest_message_rows(
        self,
        tenant_id: UUID,
        *,
        status: ConversationStatus | None = None,
        source: str | None = None,
        direction: MessageDirection | None = None,
        page: int = 1,
        page_size: int = 25,
    ) -> list[tuple[Conversation, Message]]:
        latest_messages = (
            select(
                Message.id.label("message_id"),
                func.row_number()
                .over(
                    partition_by=Message.conversation_id,
                    order_by=(Message.sent_at.desc(), Message.id.desc()),
                )
                .label("row_number"),
            )
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(Message.tenant_id == tenant_id, Conversation.tenant_id == tenant_id)
        )

        if status is not None:
            latest_messages = latest_messages.where(Conversation.status == status)
        if source is not None:
            latest_messages = latest_messages.where(Message.source == source)
        if direction is not None:
            latest_messages = latest_messages.where(Message.direction == direction)

        latest_messages_sq = latest_messages.subquery()
        result = await self.session.execute(
            select(Conversation, Message)
            .join(Message, Message.conversation_id == Conversation.id)
            .join(latest_messages_sq, latest_messages_sq.c.message_id == Message.id)
            .where(latest_messages_sq.c.row_number == 1)
            .order_by(Message.sent_at.desc(), Message.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.all())
