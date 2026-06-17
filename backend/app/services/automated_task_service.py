from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message import Message
from app.models.task import Task, TaskStatus
from app.repositories.task_repository import TaskRepository
from app.repositories.user_repository import UserRepository
from app.services.audit_log_service import AUDIT_EVENT_TASK_CREATED, AuditLogService


INBOUND_TASK_SOURCE_TYPE = "inbound_auto"
TASK_WORTHY_INTENTS = frozenset(
    {
        "complaint",
        "guest_count_change",
        "payment_issue",
        "urgent_change",
    }
)

TASK_TITLE_BY_INTENT = {
    "complaint": "Review client complaint",
    "guest_count_change": "Review guest count change",
    "payment_issue": "Verify payment status",
    "urgent_change": "Review urgent event change",
}


class AutomatedTaskService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.tasks = TaskRepository(session)
        self.users = UserRepository(session)

    async def create_for_inbound_message(
        self,
        *,
        tenant_id: UUID,
        conversation_id: UUID,
        message: Message,
    ) -> Task | None:
        if message.intent_label not in TASK_WORTHY_INTENTS:
            return None

        existing = await self.tasks.find_by_source(
            tenant_id,
            source_type=INBOUND_TASK_SOURCE_TYPE,
            source_message_id=message.id,
        )
        if existing is not None:
            return existing

        actor = await self.users.get_automation_actor_for_tenant(tenant_id)
        if actor is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="no tenant staff user available for automated task creation",
            )

        task = Task(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            message_id=message.id,
            title=TASK_TITLE_BY_INTENT[message.intent_label],
            description=_task_description(message),
            assigned_to_user_id=actor.id,
            due_at=_task_due_at(message.intent_label),
            status=TaskStatus.open,
            created_by_user_id=actor.id,
            source_type=INBOUND_TASK_SOURCE_TYPE,
            source_message_id=message.id,
        )
        await self.tasks.add(task)
        AuditLogService.record(
            self.session,
            tenant_id=tenant_id,
            actor_user_id=actor.id,
            event_type=AUDIT_EVENT_TASK_CREATED,
            resource_type="task",
            resource_id=task.id,
            details={
                "task_id": task.id,
                "conversation_id": conversation_id,
                "message_id": message.id,
                "intent_label": message.intent_label,
                "risk_level": message.risk_level,
                "source_type": INBOUND_TASK_SOURCE_TYPE,
                "automated": True,
            },
        )
        await self.session.commit()
        await self.session.refresh(task)
        return task


def _task_due_at(intent_label: str | None) -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=1)


def _task_description(message: Message) -> str:
    intent = message.intent_label or "unclassified"
    risk = message.risk_level or "unknown"
    body = message.body or ""
    return (
        "Created automatically from an inbound message.\n\n"
        f"Detected intent: {intent}\n"
        f"Risk level: {risk}\n\n"
        f"Original client message:\n{body}"
    )
