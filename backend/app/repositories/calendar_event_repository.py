from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.calendar import CalendarEvent


class CalendarEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_for_tenant(self, tenant_id: UUID, event_id: UUID) -> CalendarEvent | None:
        result = await self.session.execute(
            select(CalendarEvent)
            .where(CalendarEvent.tenant_id == tenant_id, CalendarEvent.id == event_id)
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_for_tenant(self, tenant_id: UUID) -> list[CalendarEvent]:
        result = await self.session.execute(
            select(CalendarEvent)
            .where(CalendarEvent.tenant_id == tenant_id)
            .order_by(CalendarEvent.start_time.desc(), CalendarEvent.id.desc())
        )
        return list(result.scalars().all())

    async def add(self, event: CalendarEvent) -> CalendarEvent:
        self.session.add(event)
        await self.session.flush()
        return event
