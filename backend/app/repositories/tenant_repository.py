from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.tenant import Tenant


class TenantRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, tenant_id: UUID) -> Tenant | None:
        return await self.session.get(Tenant, tenant_id)

    async def get_slug(self, tenant_id: UUID) -> str | None:
        tenant = await self.get(tenant_id)
        return tenant.slug if tenant is not None else None

    async def get_by_slug(self, slug: str) -> Tenant | None:
        result = await self.session.execute(select(Tenant).where(Tenant.slug == slug))
        return result.scalar_one_or_none()
