from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.conversations import get_tenant_conversation_or_403
from app.core.database import get_async_session
from app.core.tenant_context import TenantContext, require_role
from app.models.message import Message
from app.models.task import Task, TaskStatus
from app.models.user import User, UserRole
from app.schemas.task import TaskCreate, TaskRead, TaskUpdate
from app.services.audit_log_service import (
    AUDIT_EVENT_TASK_CREATED,
    AUDIT_EVENT_TASK_STATUS_CHANGED,
    AUDIT_EVENT_TASK_UPDATED,
    AuditLogService,
)


router = APIRouter()


async def get_tenant_task_or_403(
    task_id: UUID,
    ctx: TenantContext,
    session: AsyncSession,
) -> Task:
    task = await session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")
    if task.tenant_id != ctx.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    return task


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
async def create_task(
    payload: TaskCreate,
    ctx: TenantContext = Depends(require_role(UserRole.staff, UserRole.manager)),
    session: AsyncSession = Depends(get_async_session),
) -> Task:
    await get_tenant_conversation_or_403(payload.conversation_id, ctx, session)
    await _validate_message(payload.message_id, payload.conversation_id, ctx, session)
    await _validate_assigned_user(payload.assigned_to_user_id, ctx, session)

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
    )
    session.add(task)
    await session.flush()

    AuditLogService.record(
        session,
        tenant_id=ctx.tenant_id,
        actor_user_id=ctx.user_id,
        event_type=AUDIT_EVENT_TASK_CREATED,
        resource_type="task",
        resource_id=task.id,
        details={
            "task_id": task.id,
            "conversation_id": task.conversation_id,
            "message_id": task.message_id,
            "actor_user_id": ctx.user_id,
        },
    )
    await session.commit()
    await session.refresh(task)
    return task


@router.get("", response_model=list[TaskRead])
async def list_tasks(
    status: TaskStatus | None = None,
    conversation_id: UUID | None = None,
    assigned_to_user_id: UUID | None = None,
    ctx: TenantContext = Depends(require_role(UserRole.staff, UserRole.manager)),
    session: AsyncSession = Depends(get_async_session),
) -> list[Task]:
    stmt = select(Task).where(Task.tenant_id == ctx.tenant_id)
    if status is not None:
        stmt = stmt.where(Task.status == status)
    if conversation_id is not None:
        stmt = stmt.where(Task.conversation_id == conversation_id)
    if assigned_to_user_id is not None:
        stmt = stmt.where(Task.assigned_to_user_id == assigned_to_user_id)

    result = await session.execute(stmt.order_by(Task.created_at.desc(), Task.id.desc()))
    return list(result.scalars().all())


@router.get("/{task_id}", response_model=TaskRead)
async def get_task(
    task_id: UUID,
    ctx: TenantContext = Depends(require_role(UserRole.staff, UserRole.manager)),
    session: AsyncSession = Depends(get_async_session),
) -> Task:
    return await get_tenant_task_or_403(task_id, ctx, session)


@router.patch("/{task_id}", response_model=TaskRead)
async def update_task(
    task_id: UUID,
    payload: TaskUpdate,
    ctx: TenantContext = Depends(require_role(UserRole.staff, UserRole.manager)),
    session: AsyncSession = Depends(get_async_session),
) -> Task:
    task = await get_tenant_task_or_403(task_id, ctx, session)
    update_fields = payload.model_fields_set
    old_status = task.status

    if "assigned_to_user_id" in update_fields:
        await _validate_assigned_user(payload.assigned_to_user_id, ctx, session)

    for field in ("title", "description", "assigned_to_user_id", "due_at", "status"):
        if field in update_fields:
            setattr(task, field, getattr(payload, field))

    AuditLogService.record(
        session,
        tenant_id=ctx.tenant_id,
        actor_user_id=ctx.user_id,
        event_type=AUDIT_EVENT_TASK_UPDATED,
        resource_type="task",
        resource_id=task.id,
        details={
            "task_id": task.id,
            "conversation_id": task.conversation_id,
            "message_id": task.message_id,
            "actor_user_id": ctx.user_id,
        },
    )
    if "status" in update_fields and payload.status != old_status:
        AuditLogService.record(
            session,
            tenant_id=ctx.tenant_id,
            actor_user_id=ctx.user_id,
            event_type=AUDIT_EVENT_TASK_STATUS_CHANGED,
            resource_type="task",
            resource_id=task.id,
            details={
                "task_id": task.id,
                "conversation_id": task.conversation_id,
                "message_id": task.message_id,
                "old_status": old_status,
                "new_status": payload.status,
                "actor_user_id": ctx.user_id,
            },
        )

    await session.commit()
    await session.refresh(task)
    return task


async def _validate_message(
    message_id: UUID | None,
    conversation_id: UUID,
    ctx: TenantContext,
    session: AsyncSession,
) -> None:
    if message_id is None:
        return

    message = await session.get(Message, message_id)
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
    assigned_to_user_id: UUID | None,
    ctx: TenantContext,
    session: AsyncSession,
) -> None:
    if assigned_to_user_id is None:
        return

    user = await session.get(User, assigned_to_user_id)
    if user is None or user.tenant_id != ctx.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="assigned user not found")
