from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.core.tenant_context import TenantContext, require_role
from app.models.conversation import ConversationStatus
from app.models.message import MessageDirection
from app.models.user import UserRole
from app.schemas.inbox import (
    InboxFilters,
    InboxMessageRow,
    InboxResponse,
    InboxSummaryResponse,
)
from app.services.inbox_service import InboxService


router = APIRouter()


@router.get("", response_model=InboxResponse)
async def get_inbox(
    filters: InboxFilters = Depends(),
    ctx: TenantContext = Depends(require_role(UserRole.staff, UserRole.manager)),
    session: AsyncSession = Depends(get_async_session),
) -> InboxResponse:
    return await InboxService.get_inbox(session=session, tenant_id=ctx.tenant_id, filters=filters)


@router.get("/summary", response_model=InboxSummaryResponse)
async def get_inbox_summary(
    ctx: TenantContext = Depends(require_role(UserRole.staff, UserRole.manager)),
    session: AsyncSession = Depends(get_async_session),
) -> InboxSummaryResponse:
    return await InboxService.get_summary(session=session, tenant_id=ctx.tenant_id)


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
    return await InboxService.get_latest_message_rows(
        session=session,
        tenant_id=ctx.tenant_id,
        status=status,
        source=source,
        direction=direction,
        page=page,
        page_size=page_size,
    )
