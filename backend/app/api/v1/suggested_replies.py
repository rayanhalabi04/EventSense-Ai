from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.core.tenant_context import TenantContext, require_role
from app.models.suggested_reply import SuggestedReply
from app.models.user import UserRole
from app.schemas.suggested_reply import SuggestedReplyRead, SuggestedReplyUpdate
from app.services.suggested_reply_service import SuggestedReplyService


router = APIRouter()


async def get_tenant_suggested_reply_or_403(
    reply_id: UUID,
    ctx: TenantContext,
    session: AsyncSession,
) -> SuggestedReply:
    return await SuggestedReplyService(session).get_tenant_suggested_reply_or_403(reply_id, ctx)


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
    return await SuggestedReplyService(session).update_suggested_reply(reply_id, payload, ctx)
