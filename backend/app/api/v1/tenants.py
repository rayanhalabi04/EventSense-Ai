from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.core.tenant_context import TenantContext, require_role
from app.models.tenant import Tenant
from app.models.user import UserRole
from app.schemas.tenant import TenantRead


router = APIRouter()
admin_router = APIRouter()


@router.get("/me", response_model=TenantRead)
async def get_my_tenant(
    ctx: TenantContext = Depends(require_role(UserRole.staff, UserRole.manager)),
    session: AsyncSession = Depends(get_async_session),
) -> Tenant:
    tenant = await session.get(Tenant, ctx.tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="tenant not found")
    return tenant


@admin_router.get("/tenants", response_model=list[TenantRead])
async def list_admin_tenants(
    ctx: TenantContext = Depends(require_role(UserRole.platform_admin)),
    session: AsyncSession = Depends(get_async_session),
) -> list[Tenant]:
    result = await session.execute(select(Tenant).order_by(Tenant.slug))
    return list(result.scalars().all())
