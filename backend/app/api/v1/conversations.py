from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.core.tenant_context import TenantContext, require_role
from app.models.audit_log import AuditLog
from app.models.conversation import Conversation
from app.models.escalation import Escalation
from app.models.message import Message, MessageDirection
from app.models.task import Task
from app.models.user import UserRole
from app.schemas.conversation import (
    ConversationCreate,
    ConversationDetailAuditEvent,
    ConversationDetailMessage,
    ConversationDetailResponse,
    ConversationRead,
)
from app.models.suggested_reply import SuggestedReply
from app.schemas.escalation import EscalationRead
from app.schemas.suggested_reply import SuggestedReplyGenerateRequest, SuggestedReplyRead
from app.schemas.task import TaskRead
from app.services.audit_log_service import (
    AUDIT_EVENT_CONVERSATION_DETAIL_VIEWED,
    AuditLogService,
)
from app.services.rag_service import retrieve
from app.services.suggested_reply_service import generate_suggested_reply


router = APIRouter()


async def get_tenant_conversation_or_403(
    conversation_id: UUID,
    ctx: TenantContext,
    session: AsyncSession,
) -> Conversation:
    conversation = await session.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="conversation not found")
    if conversation.tenant_id != ctx.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    return conversation


@router.post("", response_model=ConversationRead, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    payload: ConversationCreate,
    ctx: TenantContext = Depends(require_role(UserRole.staff, UserRole.manager)),
    session: AsyncSession = Depends(get_async_session),
) -> Conversation:
    conversation = Conversation(
        tenant_id=ctx.tenant_id,
        client_name=payload.client_name,
        client_contact=payload.client_contact,
    )
    session.add(conversation)
    await session.commit()
    await session.refresh(conversation)
    return conversation


@router.get("", response_model=list[ConversationRead])
async def list_conversations(
    ctx: TenantContext = Depends(require_role(UserRole.staff, UserRole.manager)),
    session: AsyncSession = Depends(get_async_session),
) -> list[Conversation]:
    result = await session.execute(
        select(Conversation)
        .where(Conversation.tenant_id == ctx.tenant_id)
        .order_by(Conversation.created_at.desc())
    )
    return list(result.scalars().all())


@router.get("/{conversation_id}/detail", response_model=ConversationDetailResponse)
async def get_conversation_detail(
    conversation_id: UUID,
    ctx: TenantContext = Depends(require_role(UserRole.staff, UserRole.manager)),
    session: AsyncSession = Depends(get_async_session),
) -> ConversationDetailResponse:
    conversation = await get_tenant_conversation_or_403(conversation_id, ctx, session)
    messages = (
        await session.execute(
            select(Message)
            .where(Message.tenant_id == ctx.tenant_id, Message.conversation_id == conversation.id)
            .order_by(Message.sent_at.asc(), Message.id.asc())
        )
    ).scalars().all()
    latest_inbound_message = next(
        (message for message in reversed(messages) if message.direction is MessageDirection.inbound),
        None,
    )
    tasks = (
        await session.execute(
            select(Task)
            .where(Task.tenant_id == ctx.tenant_id, Task.conversation_id == conversation.id)
            .order_by(Task.created_at.desc(), Task.id.desc())
        )
    ).scalars().all()
    escalations = (
        await session.execute(
            select(Escalation)
            .where(Escalation.tenant_id == ctx.tenant_id, Escalation.conversation_id == conversation.id)
            .order_by(Escalation.created_at.desc(), Escalation.id.desc())
        )
    ).scalars().all()

    AuditLogService.record(
        session,
        tenant_id=ctx.tenant_id,
        actor_user_id=ctx.user_id,
        event_type=AUDIT_EVENT_CONVERSATION_DETAIL_VIEWED,
        resource_type="conversation",
        resource_id=conversation.id,
        details={"conversation_id": conversation.id, "user_id": ctx.user_id},
    )
    await session.flush()
    latest_reply = await _latest_suggested_reply(session, ctx.tenant_id, conversation.id)
    rag_sources: list[dict[str, object]] = []
    if latest_reply is not None and latest_reply.rag_sources:
        rag_sources = list(latest_reply.rag_sources)
    elif latest_inbound_message is not None:
        rag_result = await retrieve(
            session,
            query=latest_inbound_message.body,
            tenant_id=ctx.tenant_id,
            top_k=5,
            actor_user_id=ctx.user_id,
        )
        rag_sources = [source.to_dict() for source in rag_result.sources]

    audit_timeline = await _conversation_audit_timeline(session, ctx.tenant_id, conversation.id, messages)
    await session.commit()

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


@router.post(
    "/{conversation_id}/suggested-reply",
    response_model=SuggestedReplyRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_suggested_reply(
    conversation_id: UUID,
    payload: SuggestedReplyGenerateRequest | None = None,
    ctx: TenantContext = Depends(require_role(UserRole.staff, UserRole.manager)),
    session: AsyncSession = Depends(get_async_session),
) -> SuggestedReply:
    conversation = await get_tenant_conversation_or_403(conversation_id, ctx, session)

    requested_message_id = payload.message_id if payload is not None else None
    message = await _resolve_inbound_message(requested_message_id, conversation, ctx, session)
    if message is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="conversation has no inbound message to answer",
        )

    return await generate_suggested_reply(
        session,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        conversation=conversation,
        message=message,
    )


@router.get(
    "/{conversation_id}/suggested-replies",
    response_model=list[SuggestedReplyRead],
)
async def list_suggested_replies(
    conversation_id: UUID,
    ctx: TenantContext = Depends(require_role(UserRole.staff, UserRole.manager)),
    session: AsyncSession = Depends(get_async_session),
) -> list[SuggestedReply]:
    await get_tenant_conversation_or_403(conversation_id, ctx, session)
    result = await session.execute(
        select(SuggestedReply)
        .where(
            SuggestedReply.tenant_id == ctx.tenant_id,
            SuggestedReply.conversation_id == conversation_id,
        )
        .order_by(SuggestedReply.created_at.desc(), SuggestedReply.id.desc())
    )
    return list(result.scalars().all())


@router.get("/{conversation_id}", response_model=ConversationRead)
async def get_conversation(
    conversation_id: UUID,
    ctx: TenantContext = Depends(require_role(UserRole.staff, UserRole.manager)),
    session: AsyncSession = Depends(get_async_session),
) -> Conversation:
    return await get_tenant_conversation_or_403(conversation_id, ctx, session)


async def _resolve_inbound_message(
    requested_message_id: UUID | None,
    conversation: Conversation,
    ctx: TenantContext,
    session: AsyncSession,
) -> Message | None:
    if requested_message_id is not None:
        message = await session.get(Message, requested_message_id)
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

    result = await session.execute(
        select(Message)
        .where(
            Message.tenant_id == ctx.tenant_id,
            Message.conversation_id == conversation.id,
            Message.direction == MessageDirection.inbound,
        )
        .order_by(Message.sent_at.desc(), Message.id.desc())
        .limit(1)
    )
    return result.scalars().first()


async def _latest_suggested_reply(
    session: AsyncSession,
    tenant_id: UUID,
    conversation_id: UUID,
) -> SuggestedReply | None:
    result = await session.execute(
        select(SuggestedReply)
        .where(
            SuggestedReply.tenant_id == tenant_id,
            SuggestedReply.conversation_id == conversation_id,
        )
        .order_by(SuggestedReply.created_at.desc(), SuggestedReply.id.desc())
        .limit(1)
    )
    return result.scalars().first()


async def _conversation_audit_timeline(
    session: AsyncSession,
    tenant_id: UUID,
    conversation_id: UUID,
    messages: list[Message],
) -> list[AuditLog]:
    conversation_id_str = str(conversation_id)
    message_ids = {str(message.id) for message in messages}
    result = await session.execute(
        select(AuditLog)
        .where(AuditLog.tenant_id == tenant_id)
        .order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
    )
    audit_logs = result.scalars().all()
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
