from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.core.tenant_context import TenantContext, get_current_tenant_context
from app.models.tenant import Tenant
from app.schemas.tenant import TenantRead


router = APIRouter()


@router.get("/me", response_model=TenantRead)
async def get_my_tenant(
    ctx: TenantContext = Depends(get_current_tenant_context),
    session: AsyncSession = Depends(get_async_session),
) -> Tenant:
    tenant = await session.get(Tenant, ctx.tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="tenant not found")
    return tenant
