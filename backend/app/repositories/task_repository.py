from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task, TaskStatus


class TaskRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, task_id: UUID) -> Task | None:
        return await self.session.get(Task, task_id)

    async def list(
        self,
        tenant_id: UUID,
        *,
        status: TaskStatus | None = None,
        conversation_id: UUID | None = None,
        assigned_to_user_id: UUID | None = None,
    ) -> list[Task]:
        stmt = select(Task).where(Task.tenant_id == tenant_id)
        if status is not None:
            stmt = stmt.where(Task.status == status)
        if conversation_id is not None:
            stmt = stmt.where(Task.conversation_id == conversation_id)
        if assigned_to_user_id is not None:
            stmt = stmt.where(Task.assigned_to_user_id == assigned_to_user_id)

        result = await self.session.execute(stmt.order_by(Task.created_at.desc(), Task.id.desc()))
        return list(result.scalars().all())

    async def list_for_conversation(self, tenant_id: UUID, conversation_id: UUID) -> list[Task]:
        result = await self.session.execute(
            select(Task)
            .where(Task.tenant_id == tenant_id, Task.conversation_id == conversation_id)
            .order_by(Task.created_at.desc(), Task.id.desc())
        )
        return list(result.scalars().all())

    async def add(self, task: Task) -> Task:
        self.session.add(task)
        await self.session.flush()
        return task
