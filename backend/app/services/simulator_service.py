from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError
from app.models.conversation import Conversation, ConversationStatus
from app.models.message import Message, MessageDirection, MessageStatus
from app.services.audit_log_service import (
    AUDIT_EVENT_MESSAGE_INTENT_CLASSIFIED,
    AUDIT_EVENT_MESSAGE_RISK_DETECTED,
    AUDIT_EVENT_SIMULATOR_MESSAGE_RECEIVED,
    AUDIT_EVENT_TENANT_CROSS_TENANT_ACCESS_BLOCKED,
    AuditLogService,
)
from app.services.intent_classifier_service import IntentClassifierService
from app.services.risk_detection_service import detect_message_risk


WHATSAPP_SIMULATOR_SOURCE = "whatsapp_simulator"
SIMULATOR_MESSAGE_CREATED_EVENT = "simulator_message_created"
SimulatorEventRecorder = Callable[..., None]


@dataclass(frozen=True)
class ConversationSummary:
    id: UUID
    client_name: str
    client_contact: str | None
    status: ConversationStatus
    message_count: int
    updated_at: datetime


def emit_simulator_event(action: str, **details: Any) -> None:
    session = details.get("session")
    tenant_id = details.get("tenant_id")
    if (
        action == SIMULATOR_MESSAGE_CREATED_EVENT
        and isinstance(session, AsyncSession)
        and isinstance(tenant_id, UUID)
    ):
        actor_user_id = details.get("actor_user_id")
        AuditLogService.record(
            session,
            tenant_id=tenant_id,
            actor_user_id=actor_user_id if isinstance(actor_user_id, UUID) else None,
            event_type=AUDIT_EVENT_SIMULATOR_MESSAGE_RECEIVED,
            resource_type=(
                details.get("resource_type") if isinstance(details.get("resource_type"), str) else None
            ),
            resource_id=(
                details.get("resource_id")
                if isinstance(details.get("resource_id"), (UUID, str))
                else None
            ),
            details={
                key: value
                for key, value in details.items()
                if key not in {"session", "tenant_id", "actor_user_id", "resource_type", "resource_id"}
            },
        )
    return None


class SimulatorService:
    @staticmethod
    async def resolve_or_create_conversation(
        session: AsyncSession,
        tenant_id: UUID,
        actor_user_id: UUID | None,
        client_name: str | None,
        client_contact: str | None,
        conversation_id: UUID | None,
    ) -> tuple[Conversation, bool, bool]:
        if conversation_id is not None:
            conversation = await session.get(Conversation, conversation_id)
            if conversation is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="conversation not found",
                )
            if conversation.tenant_id != tenant_id:
                AuditLogService.record(
                    session,
                    tenant_id=tenant_id,
                    actor_user_id=actor_user_id,
                    event_type=AUDIT_EVENT_TENANT_CROSS_TENANT_ACCESS_BLOCKED,
                    resource_type="conversation",
                    resource_id=conversation.id,
                    details={"requested_conversation_tenant_id": conversation.tenant_id},
                )
                await session.commit()
                raise ForbiddenError()
            was_closed = conversation.status == ConversationStatus.closed
            if was_closed:
                conversation.status = ConversationStatus.open
            return conversation, False, was_closed

        if client_name is None or not client_name.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="client_name is required when conversation_id is not provided",
            )

        normalized_name = client_name.strip()
        query = (
            select(Conversation)
            .where(
                Conversation.tenant_id == tenant_id,
                func.lower(Conversation.client_name) == normalized_name.lower(),
            )
            .order_by(Conversation.created_at.desc())
            .limit(1)
        )
        if client_contact is None:
            query = query.where(Conversation.client_contact.is_(None))
        else:
            query = query.where(Conversation.client_contact == client_contact)

        result = await session.execute(query)
        conversation = result.scalar_one_or_none()
        if conversation is not None:
            was_closed = conversation.status == ConversationStatus.closed
            if was_closed:
                conversation.status = ConversationStatus.open
            return conversation, False, was_closed

        conversation = Conversation(
            tenant_id=tenant_id,
            client_name=normalized_name,
            client_contact=client_contact,
        )
        session.add(conversation)
        await session.flush()
        return conversation, True, False

    @staticmethod
    async def create_inbound_message(
        session: AsyncSession,
        tenant_id: UUID,
        actor_user_id: UUID | None,
        conversation: Conversation,
        body: str,
    ) -> Message:
        now = datetime.now(timezone.utc)
        conversation.updated_at = now
        message = Message(
            tenant_id=tenant_id,
            conversation_id=conversation.id,
            direction=MessageDirection.inbound,
            status=MessageStatus.unread,
            body=body,
            source=WHATSAPP_SIMULATOR_SOURCE,
            sender_user_id=None,
            sent_at=now,
        )
        session.add(message)
        await session.flush()
        classification = IntentClassifierService.classify(body)
        message.intent_label = classification.label
        message.intent_confidence = classification.confidence
        message.classified_at = now
        risk = detect_message_risk(body, classification.label)
        message.risk_level = risk.level
        message.risk_flags = risk.flags
        message.risk_reason = risk.reason
        message.risk_detected_at = now
        AuditLogService.record(
            session,
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            event_type=AUDIT_EVENT_MESSAGE_INTENT_CLASSIFIED,
            resource_type="message",
            resource_id=message.id,
            details={
                "conversation_id": conversation.id,
                "intent_label": classification.label,
                "intent_confidence": classification.confidence,
                "classified_at": now,
            },
        )
        AuditLogService.record(
            session,
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            event_type=AUDIT_EVENT_MESSAGE_RISK_DETECTED,
            resource_type="message",
            resource_id=message.id,
            details={
                "conversation_id": conversation.id,
                "risk_level": risk.level,
                "risk_flags": risk.flags,
                "risk_reason": risk.reason,
                "intent_label": classification.label,
                "risk_detected_at": now,
            },
        )
        await session.flush()
        return message

    @staticmethod
    async def list_tenant_conversations(
        session: AsyncSession,
        tenant_id: UUID,
    ) -> list[ConversationSummary]:
        message_counts = (
            select(Message.conversation_id, func.count(Message.id).label("message_count"))
            .where(Message.tenant_id == tenant_id)
            .group_by(Message.conversation_id)
            .subquery()
        )
        result = await session.execute(
            select(
                Conversation.id,
                Conversation.client_name,
                Conversation.client_contact,
                Conversation.status,
                func.coalesce(message_counts.c.message_count, 0),
                Conversation.updated_at,
            )
            .outerjoin(message_counts, message_counts.c.conversation_id == Conversation.id)
            .where(Conversation.tenant_id == tenant_id)
            .order_by(Conversation.updated_at.desc())
        )
        return [
            ConversationSummary(
                id=row[0],
                client_name=row[1],
                client_contact=row[2],
                status=row[3],
                message_count=row[4],
                updated_at=row[5],
            )
            for row in result.all()
        ]
