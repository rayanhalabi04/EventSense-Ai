from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.calendar import CalendarConnection, CalendarConnectionType, CalendarProvider


class CalendarConnectionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, connection_id: UUID) -> CalendarConnection | None:
        return await self.session.get(CalendarConnection, connection_id)

    async def get_active_for_tenant(self, tenant_id: UUID) -> CalendarConnection | None:
        result = await self.session.execute(
            select(CalendarConnection)
            .where(
                CalendarConnection.tenant_id == tenant_id,
                CalendarConnection.provider == CalendarProvider.google,
                CalendarConnection.connection_type == CalendarConnectionType.tenant_shared,
                CalendarConnection.is_active.is_(True),
            )
            .order_by(CalendarConnection.updated_at.desc(), CalendarConnection.id.desc())
            .limit(1)
        )
        return result.scalars().first()

    async def deactivate_active_for_tenant(self, tenant_id: UUID) -> int:
        result = await self.session.execute(
            select(CalendarConnection).where(
                CalendarConnection.tenant_id == tenant_id,
                CalendarConnection.provider == CalendarProvider.google,
                CalendarConnection.connection_type == CalendarConnectionType.tenant_shared,
                CalendarConnection.is_active.is_(True),
            )
        )
        connections = list(result.scalars().all())
        for connection in connections:
            connection.is_active = False
        await self.session.flush()
        return len(connections)

    async def add(self, connection: CalendarConnection) -> CalendarConnection:
        self.session.add(connection)
        await self.session.flush()
        return connection
