from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant_context import TenantContext
from app.models.conversation import Conversation
from app.models.escalation import Escalation, EscalationStatus
from app.models.message import Message
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.escalation_repository import EscalationRepository
from app.repositories.message_repository import MessageRepository
from app.repositories.user_repository import UserRepository
from app.schemas.escalation import EscalationCreate, EscalationUpdate
from app.services.audit_log_service import (
    AUDIT_EVENT_ESCALATION_CREATED,
    AUDIT_EVENT_ESCALATION_RESOLVED,
    AUDIT_EVENT_ESCALATION_STATUS_CHANGED,
    AUDIT_EVENT_ESCALATION_UPDATED,
    AuditLogService,
)


class EscalationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.conversations = ConversationRepository(session)
        self.escalations = EscalationRepository(session)
        self.messages = MessageRepository(session)
        self.users = UserRepository(session)

    async def get_tenant_escalation_or_403(
        self,
        escalation_id: UUID,
        ctx: TenantContext,
    ) -> Escalation:
        escalation = await self.escalations.get(escalation_id)
        if escalation is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="escalation not found")
        if escalation.tenant_id != ctx.tenant_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
        return escalation

    async def create_escalation(
        self,
        payload: EscalationCreate,
        ctx: TenantContext,
        *,
        source_type: str | None = None,
        source_message_id: UUID | None = None,
    ) -> Escalation:
        await self._get_tenant_conversation_or_403(payload.conversation_id, ctx)
        message = await self._get_valid_message(payload.message_id, payload.conversation_id, ctx)
        await self._validate_assigned_manager(payload.assigned_manager_user_id, ctx)

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
            source_type=source_type,
            source_message_id=source_message_id,
            resolved_at=datetime.now(timezone.utc)
            if payload.status == EscalationStatus.resolved
            else None,
        )
        await self.escalations.add(escalation)

        AuditLogService.record(
            self.session,
            tenant_id=ctx.tenant_id,
            actor_user_id=ctx.user_id,
            event_type=AUDIT_EVENT_ESCALATION_CREATED,
            resource_type="escalation",
            resource_id=escalation.id,
            details=_audit_details(escalation, ctx.user_id),
        )
        if escalation.status == EscalationStatus.resolved:
            AuditLogService.record(
                self.session,
                tenant_id=ctx.tenant_id,
                actor_user_id=ctx.user_id,
                event_type=AUDIT_EVENT_ESCALATION_RESOLVED,
                resource_type="escalation",
                resource_id=escalation.id,
                details=_audit_details(escalation, ctx.user_id),
            )

        await self.session.commit()
        await self.session.refresh(escalation)
        return escalation

    async def create_automated_escalation(
        self,
        *,
        tenant_id: UUID,
        conversation_id: UUID,
        message: Message,
        reason: str,
        ai_summary: str | None = None,
        suggested_next_step: str | None = None,
        source_type: str,
        source_message_id: UUID,
    ) -> Escalation:
        """Create a system-owned escalation from the automated inbound pipeline.

        Unlike :meth:`create_escalation` (staff-confirmed, Spec 012) this path has
        no authenticated user, so ``created_by_user_id`` is left null. It is
        idempotent on ``(source_type, source_message_id)`` so a retried webhook
        never produces a duplicate escalation. The message's intent/risk are
        snapshotted at creation time.
        """
        existing = await self.escalations.find_by_source(
            tenant_id,
            source_type=source_type,
            source_message_id=source_message_id,
        )
        if existing is not None:
            return existing

        escalation = Escalation(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            message_id=message.id,
            created_by_user_id=None,
            assigned_manager_user_id=None,
            intent_label=message.intent_label,
            risk_level=message.risk_level,
            risk_reason=message.risk_reason,
            ai_summary=ai_summary,
            suggested_next_step=suggested_next_step,
            status=EscalationStatus.open,
            source_type=source_type,
            source_message_id=source_message_id,
        )
        await self.escalations.add(escalation)

        AuditLogService.record(
            self.session,
            tenant_id=tenant_id,
            actor_user_id=None,
            event_type=AUDIT_EVENT_ESCALATION_CREATED,
            resource_type="escalation",
            resource_id=escalation.id,
            details={
                "escalation_id": escalation.id,
                "conversation_id": conversation_id,
                "message_id": message.id,
                "intent_label": message.intent_label,
                "risk_level": message.risk_level,
                "reason": reason,
                "source_type": source_type,
                "automated": True,
            },
        )
        await self.session.commit()
        await self.session.refresh(escalation)
        return escalation

    async def list_escalations(
        self,
        ctx: TenantContext,
        *,
        status: EscalationStatus | None = None,
        conversation_id: UUID | None = None,
        assigned_manager_user_id: UUID | None = None,
    ) -> list[Escalation]:
        return await self.escalations.list(
            ctx.tenant_id,
            status=status,
            conversation_id=conversation_id,
            assigned_manager_user_id=assigned_manager_user_id,
        )

    async def update_escalation(
        self,
        escalation_id: UUID,
        payload: EscalationUpdate,
        ctx: TenantContext,
    ) -> Escalation:
        escalation = await self.get_tenant_escalation_or_403(escalation_id, ctx)
        update_fields = payload.model_fields_set
        old_status = escalation.status

        if "assigned_manager_user_id" in update_fields:
            await self._validate_assigned_manager(payload.assigned_manager_user_id, ctx)

        for field in ("assigned_manager_user_id", "ai_summary", "suggested_next_step", "status"):
            if field in update_fields:
                setattr(escalation, field, getattr(payload, field))

        if "status" in update_fields:
            if payload.status == EscalationStatus.resolved and escalation.resolved_at is None:
                escalation.resolved_at = datetime.now(timezone.utc)
            elif payload.status != EscalationStatus.resolved:
                escalation.resolved_at = None

        AuditLogService.record(
            self.session,
            tenant_id=ctx.tenant_id,
            actor_user_id=ctx.user_id,
            event_type=AUDIT_EVENT_ESCALATION_UPDATED,
            resource_type="escalation",
            resource_id=escalation.id,
            details=_audit_details(escalation, ctx.user_id),
        )
        if "status" in update_fields and payload.status != old_status:
            AuditLogService.record(
                self.session,
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
                    self.session,
                    tenant_id=ctx.tenant_id,
                    actor_user_id=ctx.user_id,
                    event_type=AUDIT_EVENT_ESCALATION_RESOLVED,
                    resource_type="escalation",
                    resource_id=escalation.id,
                    details=_audit_details(escalation, ctx.user_id),
                )

        await self.session.commit()
        await self.session.refresh(escalation)
        return escalation

    async def _get_valid_message(
        self,
        message_id: UUID | None,
        conversation_id: UUID,
        ctx: TenantContext,
    ) -> Message | None:
        if message_id is None:
            return None

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
        return message

    async def _validate_assigned_manager(
        self,
        assigned_manager_user_id: UUID | None,
        ctx: TenantContext,
    ) -> None:
        if assigned_manager_user_id is None:
            return

        user = await self.users.get_manager_for_tenant(ctx.tenant_id, assigned_manager_user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="assigned manager not found",
            )

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
