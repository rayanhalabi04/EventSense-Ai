from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.core.tenant_context import TenantContext, require_role
from app.models.conversation import Conversation, ConversationStatus
from app.models.message import Message, MessageDirection
from app.models.user import UserRole
from app.schemas.inbox import InboxMessageRow


router = APIRouter()


def build_message_preview(body: str, limit: int = 120) -> str:
    normalized = " ".join(body.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 1]}..."


@router.get("/messages", response_model=list[InboxMessageRow])
async def list_inbox_messages(
    status: ConversationStatus | None = None,
    source: str | None = None,
    direction: MessageDirection | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    ctx: TenantContext = Depends(require_role(UserRole.staff, UserRole.manager)),
    session: AsyncSession = Depends(get_async_session),
) -> list[InboxMessageRow]:
    latest_message_query = (
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
        .where(Message.tenant_id == ctx.tenant_id, Conversation.tenant_id == ctx.tenant_id)
    )

    if status is not None:
        latest_message_query = latest_message_query.where(Conversation.status == status)
    if source is not None:
        latest_message_query = latest_message_query.where(Message.source == source)
    if direction is not None:
        latest_message_query = latest_message_query.where(Message.direction == direction)

    latest_message_subquery = latest_message_query.subquery()
    offset = (page - 1) * page_size

    result = await session.execute(
        select(Conversation, Message)
        .join(Message, Message.conversation_id == Conversation.id)
        .join(latest_message_subquery, latest_message_subquery.c.message_id == Message.id)
        .where(latest_message_subquery.c.row_number == 1)
        .order_by(Message.sent_at.desc(), Message.id.desc())
        .offset(offset)
        .limit(page_size)
    )

    return [
        InboxMessageRow(
            conversation_id=conversation.id,
            latest_message_id=message.id,
            client_name=conversation.client_name,
            client_contact=conversation.client_contact,
            message_preview=build_message_preview(message.body),
            latest_message_body=message.body,
            latest_message_at=message.sent_at,
            status=conversation.status,
            source=message.source,
            direction=message.direction,
        )
        for conversation, message in result.all()
    ]
