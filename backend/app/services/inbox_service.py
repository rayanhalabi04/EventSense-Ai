import math
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import ConversationStatus
from app.models.message import MessageDirection
from app.repositories.inbox_repository import InboxRepository
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
    async def get_inbox(
        session: AsyncSession,
        tenant_id: UUID,
        filters: InboxFilters,
    ) -> InboxResponse:
        repository = InboxRepository(session)
        total = await repository.count_inbox_items(tenant_id, filters)
        rows = await repository.list_inbox_rows(tenant_id, filters)

        items = [
            InboxItemResponse(
                conversation_id=row.conversation_id,
                latest_message_id=row.latest_message_id,
                client_name=row.client_name,
                client_contact=row.client_contact,
                latest_message_preview=truncate_preview(row.latest_message_body),
                latest_message_at=row.latest_message_at,
                latest_message_direction=row.latest_message_direction,
                intent_label=row.intent_label,
                intent_confidence=row.intent_confidence,
                classified_at=row.classified_at,
                risk_level=row.risk_level,
                risk_flags=row.risk_flags,
                risk_reason=row.risk_reason,
                risk_detected_at=row.risk_detected_at,
                unread_count=row.unread_count or 0,
                has_unread=(row.unread_count or 0) > 0,
                conversation_status=row.conversation_status,
                updated_at=row.updated_at,
            )
            for row in rows
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
        repository = InboxRepository(session)
        total_open = await repository.count_open_conversations(tenant_id)
        unread_or_new = await repository.count_unread_conversations(tenant_id)
        high_risk = await repository.count_high_risk_conversations(tenant_id)
        return InboxSummaryResponse(
            total_open=total_open,
            unread_or_new=unread_or_new,
            high_risk=high_risk,
        )

    @staticmethod
    async def count_unread_conversations(session: AsyncSession, tenant_id: UUID) -> int:
        return await InboxRepository(session).count_unread_conversations(tenant_id)

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
        rows = await InboxRepository(session).list_latest_message_rows(
            tenant_id,
            status=status,
            source=source,
            direction=direction,
            page=page,
            page_size=page_size,
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
                intent_label=message.intent_label,
                intent_confidence=message.intent_confidence,
                classified_at=message.classified_at,
                risk_level=message.risk_level,
                risk_flags=message.risk_flags,
                risk_reason=message.risk_reason,
                risk_detected_at=message.risk_detected_at,
            )
            for conversation, message in rows
        ]
