from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.core.tenant_context import TenantContext, require_role
from app.models.escalation import Escalation, EscalationStatus
from app.models.user import UserRole
from app.schemas.escalation import EscalationCreate, EscalationRead, EscalationUpdate
from app.services.escalation_service import EscalationService


router = APIRouter()


async def get_tenant_escalation_or_403(
    escalation_id: UUID,
    ctx: TenantContext,
    session: AsyncSession,
) -> Escalation:
    return await EscalationService(session).get_tenant_escalation_or_403(escalation_id, ctx)


@router.post("", response_model=EscalationRead, status_code=status.HTTP_201_CREATED)
async def create_escalation(
    payload: EscalationCreate,
    ctx: TenantContext = Depends(require_role(UserRole.staff, UserRole.manager)),
    session: AsyncSession = Depends(get_async_session),
) -> Escalation:
    return await EscalationService(session).create_escalation(payload, ctx)


@router.get("", response_model=list[EscalationRead])
async def list_escalations(
    status: EscalationStatus | None = None,
    conversation_id: UUID | None = None,
    assigned_manager_user_id: UUID | None = None,
    ctx: TenantContext = Depends(require_role(UserRole.staff, UserRole.manager)),
    session: AsyncSession = Depends(get_async_session),
) -> list[Escalation]:
    return await EscalationService(session).list_escalations(
        ctx,
        status=status,
        conversation_id=conversation_id,
        assigned_manager_user_id=assigned_manager_user_id,
    )


@router.get("/{escalation_id}", response_model=EscalationRead)
async def get_escalation(
    escalation_id: UUID,
    ctx: TenantContext = Depends(require_role(UserRole.staff, UserRole.manager)),
    session: AsyncSession = Depends(get_async_session),
) -> Escalation:
    return await get_tenant_escalation_or_403(escalation_id, ctx, session)


@router.patch("/{escalation_id}", response_model=EscalationRead)
async def update_escalation(
    escalation_id: UUID,
    payload: EscalationUpdate,
    ctx: TenantContext = Depends(require_role(UserRole.manager)),
    session: AsyncSession = Depends(get_async_session),
) -> Escalation:
    return await EscalationService(session).update_escalation(escalation_id, payload, ctx)
