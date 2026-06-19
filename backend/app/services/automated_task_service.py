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
from app.services.calendar_availability_parser import (
    parse_consultation_booking_confirmation,
    recent_consultation_slot_from_memory,
)
from app.services.conversation_memory_service import ConversationMemoryService


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
        consultation_slot = await self._consultation_booking_slot(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            message=message,
        )
        creates_consultation_task = consultation_slot is not None
        if message.intent_label not in TASK_WORTHY_INTENTS and not creates_consultation_task:
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
            title=(
                "Approve consultation booking"
                if creates_consultation_task
                else TASK_TITLE_BY_INTENT[message.intent_label]
            ),
            description=(
                _consultation_booking_task_description(message, consultation_slot)
                if creates_consultation_task
                else _task_description(message)
            ),
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

    async def _consultation_booking_slot(
        self,
        *,
        tenant_id: UUID,
        conversation_id: UUID,
        message: Message,
    ) -> tuple[datetime, datetime] | None:
        parsed = parse_consultation_booking_confirmation(
            message.body or "",
            reference_time=message.sent_at,
        )
        if not parsed.is_confirmation:
            return None
        if parsed.start_time is not None and parsed.end_time is not None:
            return parsed.start_time, parsed.end_time

        memory_messages = await ConversationMemoryService().load_recent(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
        )
        recent_slot = recent_consultation_slot_from_memory(
            memory_messages,
            current_message_id=str(message.id),
            reference_time=message.sent_at,
            timezone_name=parsed.timezone,
        )
        if (
            recent_slot is None
            or recent_slot.start_time is None
            or recent_slot.end_time is None
        ):
            return None
        return recent_slot.start_time, recent_slot.end_time


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


def _consultation_booking_task_description(
    message: Message,
    slot: tuple[datetime, datetime] | None,
) -> str:
    requested_time = (
        _format_task_slot(slot)
        if slot is not None
        else "Needs date/time confirmation"
    )
    body = message.body or ""
    source_label = _source_label(message.source)
    return (
        "Created automatically from a consultation booking confirmation.\n\n"
        "Type/category: calendar consultation follow-up\n"
        f"Detected intent: {message.intent_label or 'unclassified'}\n"
        f"Risk level: {message.risk_level or 'unknown'}\n"
        f"Requested date/time: {requested_time}\n"
        f"Source: {source_label}/conversation\n\n"
        f"Customer confirmation message:\n{body}\n\n"
        "Suggested action: review the request with staff approval, then create the "
        "Google Calendar event manually if approved."
    )


def _format_task_slot(slot: tuple[datetime, datetime]) -> str:
    start_time, _ = slot
    start_day = start_time.strftime("%A, %B ") + str(start_time.day)
    return f"{start_day} at {_format_task_time(start_time)}"


def _format_task_time(value: datetime) -> str:
    minute = "" if value.minute == 0 else f":{value.minute:02d}"
    hour = value.hour % 12 or 12
    suffix = "AM" if value.hour < 12 else "PM"
    return f"{hour}{minute} {suffix}"


def _source_label(source: str | None) -> str:
    if not source:
        return "Conversation"
    if source.lower() == "telegram":
        return "Telegram"
    return source.replace("_", " ").title()
