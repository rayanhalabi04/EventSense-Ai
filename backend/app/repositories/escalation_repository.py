from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.escalation import Escalation, EscalationStatus


class EscalationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, escalation_id: UUID) -> Escalation | None:
        return await self.session.get(Escalation, escalation_id)

    async def list(
        self,
        tenant_id: UUID,
        *,
        status: EscalationStatus | None = None,
        conversation_id: UUID | None = None,
        assigned_manager_user_id: UUID | None = None,
    ) -> list[Escalation]:
        stmt = select(Escalation).where(Escalation.tenant_id == tenant_id)
        if status is not None:
            stmt = stmt.where(Escalation.status == status)
        if conversation_id is not None:
            stmt = stmt.where(Escalation.conversation_id == conversation_id)
        if assigned_manager_user_id is not None:
            stmt = stmt.where(Escalation.assigned_manager_user_id == assigned_manager_user_id)

        result = await self.session.execute(
            stmt.order_by(Escalation.created_at.desc(), Escalation.id.desc())
        )
        return list(result.scalars().all())

    async def list_for_conversation(
        self,
        tenant_id: UUID,
        conversation_id: UUID,
    ) -> list[Escalation]:
        result = await self.session.execute(
            select(Escalation)
            .where(Escalation.tenant_id == tenant_id, Escalation.conversation_id == conversation_id)
            .order_by(Escalation.created_at.desc(), Escalation.id.desc())
        )
        return list(result.scalars().all())

    async def find_by_source(
        self,
        tenant_id: UUID,
        *,
        source_type: str,
        source_message_id: UUID,
    ) -> Escalation | None:
        """Return the existing escalation created from a given source (tenant-scoped),
        used to keep agent ``apply`` idempotent. At most one is expected."""
        result = await self.session.execute(
            select(Escalation)
            .where(
                Escalation.tenant_id == tenant_id,
                Escalation.source_type == source_type,
                Escalation.source_message_id == source_message_id,
            )
            .order_by(Escalation.created_at.asc(), Escalation.id.asc())
            .limit(1)
        )
        return result.scalars().first()

    async def add(self, escalation: Escalation) -> Escalation:
        self.session.add(escalation)
        await self.session.flush()
        return escalation
