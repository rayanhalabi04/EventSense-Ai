from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant_context import TenantContext
from app.models.audit_log import AuditLog
from app.models.conversation import Conversation
from app.models.message import Message, MessageDirection
from app.models.suggested_reply import SuggestedReply, SuggestedReplyStatus
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.escalation_repository import EscalationRepository
from app.repositories.message_repository import MessageRepository
from app.repositories.suggested_reply_repository import SuggestedReplyRepository
from app.repositories.task_repository import TaskRepository
from app.schemas.conversation import (
    ConversationCreate,
    ConversationDetailAuditEvent,
    ConversationDetailMessage,
    ConversationDetailResponse,
    ConversationUpdate,
)
from app.schemas.escalation import EscalationRead
from app.schemas.suggested_reply import SuggestedReplyRead
from app.schemas.task import TaskRead
from app.services.audit_log_service import (
    AUDIT_EVENT_CONVERSATION_DETAIL_VIEWED,
    AUDIT_EVENT_CONVERSATION_STATUS_CHANGED,
    AUDIT_EVENT_TELEGRAM_AUTO_REPLY_SKIPPED,
    AuditLogService,
)
from app.services.rag_service import retrieve
from app.services.suggested_reply_service import generate_suggested_reply


class ConversationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.conversations = ConversationRepository(session)
        self.messages = MessageRepository(session)
        self.tasks = TaskRepository(session)
        self.escalations = EscalationRepository(session)
        self.suggested_replies = SuggestedReplyRepository(session)
        self.audit_logs = AuditLogRepository(session)

    async def get_tenant_conversation_or_403(
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

    async def create_conversation(
        self,
        payload: ConversationCreate,
        ctx: TenantContext,
    ) -> Conversation:
        conversation = Conversation(
            tenant_id=ctx.tenant_id,
            client_name=payload.client_name,
            client_contact=payload.client_contact,
        )
        await self.conversations.add(conversation)
        await self.session.commit()
        await self.session.refresh(conversation)
        return conversation

    async def list_conversations(self, ctx: TenantContext) -> list[Conversation]:
        return await self.conversations.list(ctx.tenant_id)

    async def update_conversation(
        self,
        conversation_id: UUID,
        payload: ConversationUpdate,
        ctx: TenantContext,
    ) -> Conversation:
        conversation = await self.get_tenant_conversation_or_403(conversation_id, ctx)
        old_status = conversation.status
        conversation.status = payload.status

        AuditLogService.record(
            self.session,
            tenant_id=ctx.tenant_id,
            actor_user_id=ctx.user_id,
            event_type=AUDIT_EVENT_CONVERSATION_STATUS_CHANGED,
            resource_type="conversation",
            resource_id=conversation.id,
            details={
                "conversation_id": conversation.id,
                "old_status": old_status,
                "new_status": conversation.status,
                "user_id": ctx.user_id,
            },
        )
        await self.session.commit()
        await self.session.refresh(conversation)
        return conversation

    async def get_conversation_detail(
        self,
        conversation_id: UUID,
        ctx: TenantContext,
    ) -> ConversationDetailResponse:
        conversation = await self.get_tenant_conversation_or_403(conversation_id, ctx)
        messages = await self.messages.list_for_conversation(ctx.tenant_id, conversation.id)
        latest_inbound_message = next(
            (message for message in reversed(messages) if message.direction is MessageDirection.inbound),
            None,
        )
        tasks = await self.tasks.list_for_conversation(ctx.tenant_id, conversation.id)
        escalations = await self.escalations.list_for_conversation(ctx.tenant_id, conversation.id)

        AuditLogService.record(
            self.session,
            tenant_id=ctx.tenant_id,
            actor_user_id=ctx.user_id,
            event_type=AUDIT_EVENT_CONVERSATION_DETAIL_VIEWED,
            resource_type="conversation",
            resource_id=conversation.id,
            details={"conversation_id": conversation.id, "user_id": ctx.user_id},
        )
        await self.session.flush()
        latest_reply = await self.suggested_replies.latest_for_conversation(
            ctx.tenant_id,
            conversation.id,
        )
        rag_sources: list[dict[str, object]] = []
        if latest_reply is not None and latest_reply.rag_sources:
            rag_sources = list(latest_reply.rag_sources)
        elif latest_inbound_message is not None:
            rag_result = await retrieve(
                self.session,
                query=latest_inbound_message.body,
                tenant_id=ctx.tenant_id,
                top_k=5,
                actor_user_id=ctx.user_id,
            )
            rag_sources = [source.to_dict() for source in rag_result.sources]

        audit_timeline = await self._conversation_audit_timeline(
            ctx.tenant_id,
            conversation.id,
            messages,
        )
        auto_reply_skip_reason = _latest_auto_reply_skip_reason(latest_reply, audit_timeline)
        await self.session.commit()

        latest_message_response = (
            ConversationDetailMessage.model_validate(latest_inbound_message)
            if latest_inbound_message is not None
            else None
        )
        return ConversationDetailResponse(
            conversation_id=conversation.id,
            client_name=conversation.client_name,
            client_contact=conversation.client_contact,
            conversation_status=conversation.status,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            messages=[ConversationDetailMessage.model_validate(message) for message in messages],
            latest_inbound_message=latest_message_response,
            latest_intent_label=(
                latest_inbound_message.intent_label if latest_inbound_message is not None else None
            ),
            latest_intent_confidence=(
                latest_inbound_message.intent_confidence if latest_inbound_message is not None else None
            ),
            latest_classified_at=(
                latest_inbound_message.classified_at if latest_inbound_message is not None else None
            ),
            latest_risk_level=(
                latest_inbound_message.risk_level if latest_inbound_message is not None else None
            ),
            latest_risk_flags=(
                latest_inbound_message.risk_flags if latest_inbound_message is not None else None
            ),
            latest_risk_reason=(
                latest_inbound_message.risk_reason if latest_inbound_message is not None else None
            ),
            latest_risk_detected_at=(
                latest_inbound_message.risk_detected_at if latest_inbound_message is not None else None
            ),
            audit_timeline=[
                ConversationDetailAuditEvent.model_validate(audit_log) for audit_log in audit_timeline
            ],
            suggested_reply=(
                SuggestedReplyRead.model_validate(latest_reply) if latest_reply is not None else None
            ),
            auto_reply_skip_reason=auto_reply_skip_reason,
            rag_sources=rag_sources,
            tasks=[TaskRead.model_validate(task) for task in tasks],
            escalations=[EscalationRead.model_validate(escalation) for escalation in escalations],
        )

    async def create_suggested_reply(
        self,
        conversation_id: UUID,
        requested_message_id: UUID | None,
        ctx: TenantContext,
    ) -> SuggestedReply:
        conversation = await self.get_tenant_conversation_or_403(conversation_id, ctx)
        message = await self._resolve_inbound_message(requested_message_id, conversation, ctx)
        if message is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="conversation has no inbound message to answer",
            )

        return await generate_suggested_reply(
            self.session,
            tenant_id=ctx.tenant_id,
            user_id=ctx.user_id,
            conversation=conversation,
            message=message,
        )

    async def list_suggested_replies(
        self,
        conversation_id: UUID,
        ctx: TenantContext,
    ) -> list[SuggestedReply]:
        await self.get_tenant_conversation_or_403(conversation_id, ctx)
        return await self.suggested_replies.list_for_conversation(ctx.tenant_id, conversation_id)

    async def get_tenant_inbound_message_or_error(
        self,
        conversation_id: UUID,
        message_id: UUID,
        ctx: TenantContext,
    ) -> tuple[Conversation, Message]:
        """Resolve a specific inbound message within a tenant-owned conversation.

        Reuses the same ownership checks as suggested-reply generation:
        404 (missing), 403 (cross-tenant), 400 (message not in conversation /
        not inbound). Lets the agent endpoint avoid duplicating this logic.
        """
        conversation = await self.get_tenant_conversation_or_403(conversation_id, ctx)
        message = await self._resolve_inbound_message(message_id, conversation, ctx)
        # ``message`` is only None when no message_id is supplied; here it is required.
        assert message is not None
        return conversation, message

    async def _resolve_inbound_message(
        self,
        requested_message_id: UUID | None,
        conversation: Conversation,
        ctx: TenantContext,
    ) -> Message | None:
        if requested_message_id is not None:
            message = await self.messages.get(requested_message_id)
            if message is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="message not found")
            if message.tenant_id != ctx.tenant_id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
            if message.conversation_id != conversation.id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="message does not belong to conversation",
                )
            if message.direction != MessageDirection.inbound:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="suggested replies can only be generated for inbound messages",
                )
            return message

        return await self.messages.latest_inbound_for_conversation(ctx.tenant_id, conversation.id)

    async def _conversation_audit_timeline(
        self,
        tenant_id: UUID,
        conversation_id: UUID,
        messages: list[Message],
    ) -> list[AuditLog]:
        conversation_id_str = str(conversation_id)
        message_ids = {str(message.id) for message in messages}
        audit_logs = await self.audit_logs.list_for_tenant_ordered(tenant_id)
        return [
            audit_log
            for audit_log in audit_logs
            if _audit_log_matches_conversation(audit_log, conversation_id_str, message_ids)
        ]


def _latest_auto_reply_skip_reason(
    latest_reply: SuggestedReply | None,
    audit_timeline: list[AuditLog],
) -> str | None:
    """Reason the Telegram auto-reply was skipped, for the *current* pending draft.

    Only surfaced when the latest suggested reply is a pending draft that was not
    auto-sent (so a successful auto-send or human action never shows a stale skip
    reason). ``audit_timeline`` is ordered oldest-first, so we scan from the end
    to pick the most recent skip event.
    """
    if (
        latest_reply is None
        or latest_reply.auto_sent_at is not None
        or latest_reply.status != SuggestedReplyStatus.draft
    ):
        return None
    for audit_log in reversed(audit_timeline):
        if audit_log.event_type == AUDIT_EVENT_TELEGRAM_AUTO_REPLY_SKIPPED:
            if audit_log.details.get("suggested_reply_id") != str(latest_reply.id):
                continue
            reason = audit_log.details.get("reason")
            return str(reason) if reason is not None else None
    return None


def _audit_log_matches_conversation(
    audit_log: AuditLog,
    conversation_id: str,
    message_ids: set[str],
) -> bool:
    if audit_log.resource_type == "conversation" and audit_log.resource_id == conversation_id:
        return True
    if audit_log.resource_type == "message" and audit_log.resource_id in message_ids:
        return True
    if audit_log.details.get("conversation_id") == conversation_id:
        return True
    return False
