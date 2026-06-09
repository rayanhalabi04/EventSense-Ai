import math
from uuid import UUID

from sqlalchemy import exists, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.conversation import Conversation, ConversationStatus
from app.models.message import Message, MessageDirection, MessageStatus
from app.schemas.inbox import (
    InboxFilters,
    InboxItemResponse,
    InboxMessageRow,
    InboxResponse,
    InboxSummaryResponse,
)


def truncate_preview(body: str | None, max_len: int = 100) -> str | None:
    if body is None:
        return None
    if len(body) <= max_len:
        return body
    return f"{body[: max_len - 3]}..."


class InboxService:
    @staticmethod
    def _latest_message_id_subquery(tenant_id: UUID):
        LatestMessage = aliased(Message)
        return (
            select(LatestMessage.id)
            .where(
                LatestMessage.conversation_id == Conversation.id,
                LatestMessage.tenant_id == tenant_id,
            )
            .order_by(LatestMessage.sent_at.desc(), LatestMessage.id.desc())
            .limit(1)
            .correlate(Conversation)
            .scalar_subquery()
        )

    @staticmethod
    def _unread_count_subquery(tenant_id: UUID):
        UnreadMessage = aliased(Message)
        return (
            select(func.count(UnreadMessage.id))
            .where(
                UnreadMessage.conversation_id == Conversation.id,
                UnreadMessage.tenant_id == tenant_id,
                UnreadMessage.status == MessageStatus.unread,
            )
            .correlate(Conversation)
            .scalar_subquery()
        )

    @staticmethod
    def _base_inbox_statement(tenant_id: UUID, filters: InboxFilters):
        latest_message_id = InboxService._latest_message_id_subquery(tenant_id)
        unread_count = InboxService._unread_count_subquery(tenant_id)
        LatestMessage = aliased(Message)

        stmt = (
            select(
                Conversation.id.label("conversation_id"),
                Conversation.client_name,
                Conversation.client_contact,
                Conversation.status.label("conversation_status"),
                Conversation.updated_at,
                LatestMessage.id.label("latest_message_id"),
                LatestMessage.body.label("latest_message_body"),
                LatestMessage.sent_at.label("latest_message_at"),
                LatestMessage.direction.label("latest_message_direction"),
                unread_count.label("unread_count"),
            )
            .outerjoin(LatestMessage, LatestMessage.id == latest_message_id)
            .where(Conversation.tenant_id == tenant_id)
        )

        if filters.status is not None:
            stmt = stmt.where(Conversation.status == filters.status)
        if filters.unread_only:
            stmt = stmt.where(unread_count > 0)
        if filters.search is not None and len(filters.search) >= 2:
            pattern = f"%{filters.search}%"
            SearchMessage = aliased(Message)
            message_match = exists(
                select(literal(1)).where(
                    SearchMessage.conversation_id == Conversation.id,
                    SearchMessage.tenant_id == tenant_id,
                    SearchMessage.body.ilike(pattern),
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

    @staticmethod
    async def get_inbox(
        session: AsyncSession,
        tenant_id: UUID,
        filters: InboxFilters,
    ) -> InboxResponse:
        base_stmt = InboxService._base_inbox_statement(tenant_id, filters)
        total = (
            await session.execute(select(func.count()).select_from(base_stmt.subquery()))
        ).scalar_one()

        result = await session.execute(
            base_stmt.order_by(Conversation.updated_at.desc(), Conversation.id.desc())
            .offset((filters.page - 1) * filters.page_size)
            .limit(filters.page_size)
        )

        items = [
            InboxItemResponse(
                conversation_id=row.conversation_id,
                latest_message_id=row.latest_message_id,
                client_name=row.client_name,
                client_contact=row.client_contact,
                latest_message_preview=truncate_preview(row.latest_message_body),
                latest_message_at=row.latest_message_at,
                latest_message_direction=row.latest_message_direction,
                unread_count=row.unread_count or 0,
                has_unread=(row.unread_count or 0) > 0,
                conversation_status=row.conversation_status,
                updated_at=row.updated_at,
            )
            for row in result.all()
        ]

        total_unread = await InboxService.count_unread_conversations(session, tenant_id)
        return InboxResponse(
            items=items,
            total=total,
            total_unread=total_unread,
            page=filters.page,
            page_size=filters.page_size,
            total_pages=math.ceil(total / filters.page_size) if total else 0,
        )

    @staticmethod
    async def get_summary(session: AsyncSession, tenant_id: UUID) -> InboxSummaryResponse:
        total_open = (
            await session.execute(
                select(func.count(Conversation.id)).where(
                    Conversation.tenant_id == tenant_id,
                    Conversation.status == ConversationStatus.open,
                )
            )
        ).scalar_one()
        unread_or_new = await InboxService.count_unread_conversations(session, tenant_id)
        return InboxSummaryResponse(total_open=total_open, unread_or_new=unread_or_new)

    @staticmethod
    async def count_unread_conversations(session: AsyncSession, tenant_id: UUID) -> int:
        return (
            await session.execute(
                select(func.count(func.distinct(Message.conversation_id))).where(
                    Message.tenant_id == tenant_id,
                    Message.status == MessageStatus.unread,
                )
            )
        ).scalar_one()

    @staticmethod
    async def get_latest_message_rows(
        session: AsyncSession,
        tenant_id: UUID,
        *,
        status: ConversationStatus | None = None,
        source: str | None = None,
        direction: MessageDirection | None = None,
        page: int = 1,
        page_size: int = 25,
    ) -> list[InboxMessageRow]:
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
        result = await session.execute(
            select(Conversation, Message)
            .join(Message, Message.conversation_id == Conversation.id)
            .join(latest_messages_sq, latest_messages_sq.c.message_id == Message.id)
            .where(latest_messages_sq.c.row_number == 1)
            .order_by(Message.sent_at.desc(), Message.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )

        return [
            InboxMessageRow(
                conversation_id=conversation.id,
                latest_message_id=message.id,
                client_name=conversation.client_name,
                client_contact=conversation.client_contact,
                message_preview=truncate_preview(message.body, max_len=120) or "",
                latest_message_body=message.body,
                latest_message_at=message.sent_at,
                status=conversation.status,
                source=message.source,
                direction=message.direction,
            )
            for conversation, message in result.all()
        ]
