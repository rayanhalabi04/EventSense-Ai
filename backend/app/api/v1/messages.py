from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.conversations import get_tenant_conversation_or_403
from app.core.database import get_async_session
from app.core.tenant_context import TenantContext, require_role
from app.models.message import Message, MessageDirection
from app.models.user import UserRole
from app.schemas.message import MessageCreate, MessageRead


router = APIRouter()


@router.post("/{conversation_id}/messages", response_model=MessageRead, status_code=status.HTTP_201_CREATED)
async def create_message(
    conversation_id: UUID,
    payload: MessageCreate,
    ctx: TenantContext = Depends(require_role(UserRole.staff, UserRole.manager)),
    session: AsyncSession = Depends(get_async_session),
) -> Message:
    await get_tenant_conversation_or_403(conversation_id, ctx, session)
    direction = payload.direction
    sender_user_id = ctx.user_id if direction == MessageDirection.outbound else None
    message = Message(
        tenant_id=ctx.tenant_id,
        conversation_id=conversation_id,
        direction=direction,
        body=payload.body,
        sender_user_id=sender_user_id,
        sent_at=datetime.now(timezone.utc),
    )
    session.add(message)
    await session.commit()
    await session.refresh(message)
    return message


@router.get("/{conversation_id}/messages", response_model=list[MessageRead])
async def list_messages(
    conversation_id: UUID,
    ctx: TenantContext = Depends(require_role(UserRole.staff, UserRole.manager)),
    session: AsyncSession = Depends(get_async_session),
) -> list[Message]:
    await get_tenant_conversation_or_403(conversation_id, ctx, session)
    result = await session.execute(
        select(Message)
        .where(Message.tenant_id == ctx.tenant_id, Message.conversation_id == conversation_id)
        .order_by(Message.sent_at.asc())
    )
    return list(result.scalars().all())
