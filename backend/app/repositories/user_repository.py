from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, UserRole


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, user_id: UUID) -> User | None:
        return await self.session.get(User, user_id)

    async def get_for_tenant(self, tenant_id: UUID, user_id: UUID) -> User | None:
        user = await self.get(user_id)
        if user is None or user.tenant_id != tenant_id:
            return None
        return user

    async def get_manager_for_tenant(self, tenant_id: UUID, user_id: UUID) -> User | None:
        user = await self.get_for_tenant(tenant_id, user_id)
        if user is None or user.role != UserRole.manager:
            return None
        return user

    async def get_automation_actor_for_tenant(self, tenant_id: UUID) -> User | None:
        manager_result = await self.session.execute(
            select(User)
            .where(
                User.tenant_id == tenant_id,
                User.is_active.is_(True),
                User.role == UserRole.manager,
            )
            .order_by(User.created_at.asc(), User.id.asc())
        )
        manager = manager_result.scalars().first()
        if manager is not None:
            return manager

        staff_result = await self.session.execute(
            select(User)
            .where(
                User.tenant_id == tenant_id,
                User.is_active.is_(True),
                User.role == UserRole.staff,
            )
            .order_by(User.created_at.asc(), User.id.asc())
        )
        return staff_result.scalars().first()
