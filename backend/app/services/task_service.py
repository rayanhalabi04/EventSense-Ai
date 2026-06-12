from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant_context import TenantContext
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.task import Task, TaskStatus
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.message_repository import MessageRepository
from app.repositories.task_repository import TaskRepository
from app.repositories.user_repository import UserRepository
from app.schemas.task import TaskCreate, TaskUpdate
from app.services.audit_log_service import (
    AUDIT_EVENT_TASK_CREATED,
    AUDIT_EVENT_TASK_STATUS_CHANGED,
    AUDIT_EVENT_TASK_UPDATED,
    AuditLogService,
)


class TaskService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.conversations = ConversationRepository(session)
        self.tasks = TaskRepository(session)
        self.messages = MessageRepository(session)
        self.users = UserRepository(session)

    async def get_tenant_task_or_403(self, task_id: UUID, ctx: TenantContext) -> Task:
        task = await self.tasks.get(task_id)
        if task is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")
        if task.tenant_id != ctx.tenant_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
        return task

    async def create_task(
        self,
        payload: TaskCreate,
        ctx: TenantContext,
        *,
        source_type: str | None = None,
        source_message_id: UUID | None = None,
    ) -> Task:
        await self._get_tenant_conversation_or_403(payload.conversation_id, ctx)
        await self._validate_message(payload.message_id, payload.conversation_id, ctx)
        await self._validate_assigned_user(payload.assigned_to_user_id, ctx)

        task = Task(
            tenant_id=ctx.tenant_id,
            conversation_id=payload.conversation_id,
            message_id=payload.message_id,
            title=payload.title,
            description=payload.description,
            assigned_to_user_id=payload.assigned_to_user_id,
            due_at=payload.due_at,
            status=payload.status,
            created_by_user_id=ctx.user_id,
            source_type=source_type,
            source_message_id=source_message_id,
        )
        await self.tasks.add(task)

        AuditLogService.record(
            self.session,
            tenant_id=ctx.tenant_id,
            actor_user_id=ctx.user_id,
            event_type=AUDIT_EVENT_TASK_CREATED,
            resource_type="task",
            resource_id=task.id,
            details=_audit_details(task, ctx.user_id),
        )
        await self.session.commit()
        await self.session.refresh(task)
        return task

    async def list_tasks(
        self,
        ctx: TenantContext,
        *,
        status: TaskStatus | None = None,
        conversation_id: UUID | None = None,
        assigned_to_user_id: UUID | None = None,
    ) -> list[Task]:
        return await self.tasks.list(
            ctx.tenant_id,
            status=status,
            conversation_id=conversation_id,
            assigned_to_user_id=assigned_to_user_id,
        )

    async def update_task(self, task_id: UUID, payload: TaskUpdate, ctx: TenantContext) -> Task:
        task = await self.get_tenant_task_or_403(task_id, ctx)
        update_fields = payload.model_fields_set
        old_status = task.status

        if "assigned_to_user_id" in update_fields:
            await self._validate_assigned_user(payload.assigned_to_user_id, ctx)

        for field in ("title", "description", "assigned_to_user_id", "due_at", "status"):
            if field in update_fields:
                setattr(task, field, getattr(payload, field))

        AuditLogService.record(
            self.session,
            tenant_id=ctx.tenant_id,
            actor_user_id=ctx.user_id,
            event_type=AUDIT_EVENT_TASK_UPDATED,
            resource_type="task",
            resource_id=task.id,
            details=_audit_details(task, ctx.user_id),
        )
        if "status" in update_fields and payload.status != old_status:
            AuditLogService.record(
                self.session,
                tenant_id=ctx.tenant_id,
                actor_user_id=ctx.user_id,
                event_type=AUDIT_EVENT_TASK_STATUS_CHANGED,
                resource_type="task",
                resource_id=task.id,
                details={
                    **_audit_details(task, ctx.user_id),
                    "old_status": old_status,
                    "new_status": payload.status,
                },
            )

        await self.session.commit()
        await self.session.refresh(task)
        return task

    async def _validate_message(
        self,
        message_id: UUID | None,
        conversation_id: UUID,
        ctx: TenantContext,
    ) -> None:
        if message_id is None:
            return

        message = await self.messages.get(message_id)
        if message is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="message not found")
        if message.tenant_id != ctx.tenant_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
        if message.conversation_id != conversation_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="message does not belong to conversation",
            )

    async def _validate_assigned_user(
        self,
        assigned_to_user_id: UUID | None,
        ctx: TenantContext,
    ) -> None:
        if assigned_to_user_id is None:
            return

        user = await self.users.get_for_tenant(ctx.tenant_id, assigned_to_user_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="assigned user not found")

    async def _get_tenant_conversation_or_403(
        self,
        conversation_id: UUID,
        ctx: TenantContext,
    ) -> Conversation:
        conversation = await self.conversations.get(conversation_id)
        if conversation is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="conversation not found")
        if conversation.tenant_id != ctx.tenant_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
        return conversation


def _audit_details(task: Task, actor_user_id: UUID) -> dict[str, object]:
    return {
        "task_id": task.id,
        "conversation_id": task.conversation_id,
        "message_id": task.message_id,
        "actor_user_id": actor_user_id,
    }
