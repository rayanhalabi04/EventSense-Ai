from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.core.tenant_context import TenantContext, require_role
from app.models.task import Task, TaskStatus
from app.models.user import UserRole
from app.schemas.task import TaskCreate, TaskRead, TaskUpdate
from app.services.task_service import TaskService


router = APIRouter()


async def get_tenant_task_or_403(
    task_id: UUID,
    ctx: TenantContext,
    session: AsyncSession,
) -> Task:
    return await TaskService(session).get_tenant_task_or_403(task_id, ctx)


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
async def create_task(
    payload: TaskCreate,
    ctx: TenantContext = Depends(require_role(UserRole.staff, UserRole.manager)),
    session: AsyncSession = Depends(get_async_session),
) -> Task:
    return await TaskService(session).create_task(payload, ctx)


@router.get("", response_model=list[TaskRead])
async def list_tasks(
    status: TaskStatus | None = None,
    conversation_id: UUID | None = None,
    assigned_to_user_id: UUID | None = None,
    ctx: TenantContext = Depends(require_role(UserRole.staff, UserRole.manager)),
    session: AsyncSession = Depends(get_async_session),
) -> list[Task]:
    return await TaskService(session).list_tasks(
        ctx,
        status=status,
        conversation_id=conversation_id,
        assigned_to_user_id=assigned_to_user_id,
    )


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
    return await TaskService(session).update_task(task_id, payload, ctx)
