from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.core.tenant_context import TenantContext, require_role
from app.models.user import UserRole
from app.schemas.audit_log import AuditLogRead
from app.services.audit_log_service import AuditLogService


router = APIRouter()


@router.get("", response_model=list[AuditLogRead])
async def list_audit_logs(
    ctx: TenantContext = Depends(require_role(UserRole.manager, UserRole.platform_admin)),
    session: AsyncSession = Depends(get_async_session),
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AuditLogRead]:
    return await AuditLogService.list_for_tenant(
        session,
        tenant_id=ctx.tenant_id,
        limit=limit,
        offset=offset,
    )
