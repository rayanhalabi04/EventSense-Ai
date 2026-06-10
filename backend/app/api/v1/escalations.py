from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.conversations import get_tenant_conversation_or_403
from app.core.database import get_async_session
from app.core.tenant_context import TenantContext, require_role
from app.models.escalation import Escalation, EscalationStatus
from app.models.message import Message
from app.models.user import User, UserRole
from app.schemas.escalation import EscalationCreate, EscalationRead, EscalationUpdate
from app.services.audit_log_service import (
    AUDIT_EVENT_ESCALATION_CREATED,
    AUDIT_EVENT_ESCALATION_RESOLVED,
    AUDIT_EVENT_ESCALATION_STATUS_CHANGED,
    AUDIT_EVENT_ESCALATION_UPDATED,
    AuditLogService,
)


router = APIRouter()


async def get_tenant_escalation_or_403(
    escalation_id: UUID,
    ctx: TenantContext,
    session: AsyncSession,
) -> Escalation:
    escalation = await session.get(Escalation, escalation_id)
    if escalation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="escalation not found")
    if escalation.tenant_id != ctx.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    return escalation


@router.post("", response_model=EscalationRead, status_code=status.HTTP_201_CREATED)
async def create_escalation(
    payload: EscalationCreate,
    ctx: TenantContext = Depends(require_role(UserRole.staff, UserRole.manager)),
    session: AsyncSession = Depends(get_async_session),
) -> Escalation:
    await get_tenant_conversation_or_403(payload.conversation_id, ctx, session)
    message = await _get_valid_message(payload.message_id, payload.conversation_id, ctx, session)
    await _validate_assigned_manager(payload.assigned_manager_user_id, ctx, session)

    escalation = Escalation(
        tenant_id=ctx.tenant_id,
        conversation_id=payload.conversation_id,
        message_id=payload.message_id,
        created_by_user_id=ctx.user_id,
        assigned_manager_user_id=payload.assigned_manager_user_id,
        intent_label=message.intent_label if message is not None else None,
        risk_level=message.risk_level if message is not None else None,
        risk_reason=message.risk_reason if message is not None else None,
        ai_summary=payload.ai_summary,
        suggested_next_step=payload.suggested_next_step,
        status=payload.status,
        resolved_at=datetime.now(timezone.utc)
        if payload.status == EscalationStatus.resolved
        else None,
    )
    session.add(escalation)
    await session.flush()

    AuditLogService.record(
        session,
        tenant_id=ctx.tenant_id,
        actor_user_id=ctx.user_id,
        event_type=AUDIT_EVENT_ESCALATION_CREATED,
        resource_type="escalation",
        resource_id=escalation.id,
        details=_audit_details(escalation, ctx.user_id),
    )
    if escalation.status == EscalationStatus.resolved:
        AuditLogService.record(
            session,
            tenant_id=ctx.tenant_id,
            actor_user_id=ctx.user_id,
            event_type=AUDIT_EVENT_ESCALATION_RESOLVED,
            resource_type="escalation",
            resource_id=escalation.id,
            details=_audit_details(escalation, ctx.user_id),
        )

    await session.commit()
    await session.refresh(escalation)
    return escalation


@router.get("", response_model=list[EscalationRead])
async def list_escalations(
    status: EscalationStatus | None = None,
    conversation_id: UUID | None = None,
    assigned_manager_user_id: UUID | None = None,
    ctx: TenantContext = Depends(require_role(UserRole.staff, UserRole.manager)),
    session: AsyncSession = Depends(get_async_session),
) -> list[Escalation]:
    stmt = select(Escalation).where(Escalation.tenant_id == ctx.tenant_id)
    if status is not None:
        stmt = stmt.where(Escalation.status == status)
    if conversation_id is not None:
        stmt = stmt.where(Escalation.conversation_id == conversation_id)
    if assigned_manager_user_id is not None:
        stmt = stmt.where(Escalation.assigned_manager_user_id == assigned_manager_user_id)

    result = await session.execute(stmt.order_by(Escalation.created_at.desc(), Escalation.id.desc()))
    return list(result.scalars().all())


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
    escalation = await get_tenant_escalation_or_403(escalation_id, ctx, session)
    update_fields = payload.model_fields_set
    old_status = escalation.status

    if "assigned_manager_user_id" in update_fields:
        await _validate_assigned_manager(payload.assigned_manager_user_id, ctx, session)

    for field in ("assigned_manager_user_id", "ai_summary", "suggested_next_step", "status"):
        if field in update_fields:
            setattr(escalation, field, getattr(payload, field))

    if "status" in update_fields:
        if payload.status == EscalationStatus.resolved and escalation.resolved_at is None:
            escalation.resolved_at = datetime.now(timezone.utc)
        elif payload.status != EscalationStatus.resolved:
            escalation.resolved_at = None

    AuditLogService.record(
        session,
        tenant_id=ctx.tenant_id,
        actor_user_id=ctx.user_id,
        event_type=AUDIT_EVENT_ESCALATION_UPDATED,
        resource_type="escalation",
        resource_id=escalation.id,
        details=_audit_details(escalation, ctx.user_id),
    )
    if "status" in update_fields and payload.status != old_status:
        AuditLogService.record(
            session,
            tenant_id=ctx.tenant_id,
            actor_user_id=ctx.user_id,
            event_type=AUDIT_EVENT_ESCALATION_STATUS_CHANGED,
            resource_type="escalation",
            resource_id=escalation.id,
            details={
                **_audit_details(escalation, ctx.user_id),
                "old_status": old_status,
                "new_status": payload.status,
            },
        )
        if payload.status == EscalationStatus.resolved:
            AuditLogService.record(
                session,
                tenant_id=ctx.tenant_id,
                actor_user_id=ctx.user_id,
                event_type=AUDIT_EVENT_ESCALATION_RESOLVED,
                resource_type="escalation",
                resource_id=escalation.id,
                details=_audit_details(escalation, ctx.user_id),
            )

    await session.commit()
    await session.refresh(escalation)
    return escalation


async def _get_valid_message(
    message_id: UUID | None,
    conversation_id: UUID,
    ctx: TenantContext,
    session: AsyncSession,
) -> Message | None:
    if message_id is None:
        return None

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
    return message


async def _validate_assigned_manager(
    assigned_manager_user_id: UUID | None,
    ctx: TenantContext,
    session: AsyncSession,
) -> None:
    if assigned_manager_user_id is None:
        return

    user = await session.get(User, assigned_manager_user_id)
    if user is None or user.tenant_id != ctx.tenant_id or user.role != UserRole.manager:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="assigned manager not found",
        )


def _audit_details(escalation: Escalation, actor_user_id: UUID) -> dict[str, object]:
    details: dict[str, object] = {
        "escalation_id": escalation.id,
        "conversation_id": escalation.conversation_id,
        "message_id": escalation.message_id,
        "actor_user_id": actor_user_id,
    }
    if escalation.assigned_manager_user_id is not None:
        details["assigned_manager_user_id"] = escalation.assigned_manager_user_id
    return details
