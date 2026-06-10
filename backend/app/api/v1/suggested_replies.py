from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.core.tenant_context import TenantContext, require_role
from app.models.suggested_reply import SuggestedReply, SuggestedReplyStatus
from app.models.user import UserRole
from app.schemas.suggested_reply import SuggestedReplyRead, SuggestedReplyUpdate
from app.services.audit_log_service import (
    AUDIT_EVENT_SUGGESTED_REPLY_APPROVED,
    AUDIT_EVENT_SUGGESTED_REPLY_EDITED,
    AUDIT_EVENT_SUGGESTED_REPLY_REJECTED,
    AuditLogService,
)


router = APIRouter()


async def get_tenant_suggested_reply_or_403(
    reply_id: UUID,
    ctx: TenantContext,
    session: AsyncSession,
) -> SuggestedReply:
    reply = await session.get(SuggestedReply, reply_id)
    if reply is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="suggested reply not found")
    if reply.tenant_id != ctx.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    return reply


@router.get("/{reply_id}", response_model=SuggestedReplyRead)
async def get_suggested_reply(
    reply_id: UUID,
    ctx: TenantContext = Depends(require_role(UserRole.staff, UserRole.manager)),
    session: AsyncSession = Depends(get_async_session),
) -> SuggestedReply:
    return await get_tenant_suggested_reply_or_403(reply_id, ctx, session)


@router.patch("/{reply_id}", response_model=SuggestedReplyRead)
async def update_suggested_reply(
    reply_id: UUID,
    payload: SuggestedReplyUpdate,
    ctx: TenantContext = Depends(require_role(UserRole.staff, UserRole.manager)),
    session: AsyncSession = Depends(get_async_session),
) -> SuggestedReply:
    reply = await get_tenant_suggested_reply_or_403(reply_id, ctx, session)
    update_fields = payload.model_fields_set

    text_edited = "suggested_text" in update_fields and payload.suggested_text != reply.suggested_text
    if "suggested_text" in update_fields:
        reply.suggested_text = payload.suggested_text

    # A bare text change with no explicit status means the staff member edited it.
    new_status = payload.status if "status" in update_fields else None
    if new_status is None and text_edited:
        new_status = SuggestedReplyStatus.edited

    if new_status is not None:
        reply.status = new_status
        if new_status == SuggestedReplyStatus.approved:
            reply.approved_by_user_id = ctx.user_id

    await session.flush()

    base_details: dict[str, object] = {
        "suggested_reply_id": reply.id,
        "conversation_id": reply.conversation_id,
        "message_id": reply.message_id,
        "answer_supported": reply.answer_supported,
        "source_document_ids": reply.source_document_ids,
        "user_id": ctx.user_id,
    }

    if new_status == SuggestedReplyStatus.approved:
        AuditLogService.record(
            session,
            tenant_id=ctx.tenant_id,
            actor_user_id=ctx.user_id,
            event_type=AUDIT_EVENT_SUGGESTED_REPLY_APPROVED,
            resource_type="suggested_reply",
            resource_id=reply.id,
            details=base_details,
        )
    elif new_status == SuggestedReplyStatus.rejected:
        AuditLogService.record(
            session,
            tenant_id=ctx.tenant_id,
            actor_user_id=ctx.user_id,
            event_type=AUDIT_EVENT_SUGGESTED_REPLY_REJECTED,
            resource_type="suggested_reply",
            resource_id=reply.id,
            details=base_details,
        )
    elif new_status == SuggestedReplyStatus.edited or text_edited:
        AuditLogService.record(
            session,
            tenant_id=ctx.tenant_id,
            actor_user_id=ctx.user_id,
            event_type=AUDIT_EVENT_SUGGESTED_REPLY_EDITED,
            resource_type="suggested_reply",
            resource_id=reply.id,
            details=base_details,
        )

    await session.commit()
    await session.refresh(reply)
    return reply
