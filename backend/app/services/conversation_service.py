from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant_context import TenantContext
from app.models.audit_log import AuditLog
from app.models.conversation import Conversation
from app.models.message import Message, MessageDirection
from app.models.suggested_reply import SuggestedReply
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
)
from app.schemas.escalation import EscalationRead
from app.schemas.suggested_reply import SuggestedReplyRead
from app.schemas.task import TaskRead
from app.services.audit_log_service import (
    AUDIT_EVENT_CONVERSATION_DETAIL_VIEWED,
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
