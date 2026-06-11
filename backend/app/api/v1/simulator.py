from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.core.tenant_context import TenantContext, require_role
from app.models.user import UserRole
from app.schemas.simulator import (
    SimulatorConversationItem,
    SimulatorConversationsResponse,
    SimulatorMessageRequest,
    SimulatorMessageResponse,
)
from app.services.simulator_service import (
    SIMULATOR_MESSAGE_CREATED_EVENT,
    SimulatorService,
    emit_simulator_event,
)
from app.services.conversation_memory_service import ConversationMemoryService


router = APIRouter()


@router.post("/messages", response_model=SimulatorMessageResponse, status_code=status.HTTP_201_CREATED)
async def simulate_whatsapp_message(
    payload: SimulatorMessageRequest,
    ctx: TenantContext = Depends(require_role(UserRole.staff, UserRole.manager)),
    session: AsyncSession = Depends(get_async_session),
) -> SimulatorMessageResponse:
    conversation, is_new_conversation, was_closed = (
        await SimulatorService.resolve_or_create_conversation(
            session=session,
            tenant_id=ctx.tenant_id,
            actor_user_id=ctx.user_id,
            client_name=payload.client_name,
            client_contact=payload.client_contact,
            conversation_id=payload.conversation_id,
        )
    )
    message = await SimulatorService.create_inbound_message(
        session=session,
        tenant_id=ctx.tenant_id,
        actor_user_id=ctx.user_id,
        conversation=conversation,
        body=payload.body,
    )
    emit_simulator_event(
        SIMULATOR_MESSAGE_CREATED_EVENT,
        session=session,
        actor_user_id=ctx.user_id,
        tenant_id=ctx.tenant_id,
        resource_type="message",
        resource_id=message.id,
        conversation_id=conversation.id,
        client_name=payload.client_name or conversation.client_name,
        is_new_conversation=is_new_conversation,
        reopened=was_closed,
    )
    await session.commit()
    await session.refresh(conversation)
    await session.refresh(message)
    await ConversationMemoryService().store_inbound_message(
        tenant_id=ctx.tenant_id,
        message=message,
    )
    return SimulatorMessageResponse(
        message_id=message.id,
        conversation_id=conversation.id,
        is_new_conversation=is_new_conversation,
        conversation_status=conversation.status.value,
        tenant_id=ctx.tenant_id,
        intent_label=message.intent_label,
        intent_confidence=message.intent_confidence,
        classified_at=message.classified_at,
        risk_level=message.risk_level,
        risk_flags=message.risk_flags,
        risk_reason=message.risk_reason,
        risk_detected_at=message.risk_detected_at,
    )


@router.get("/conversations", response_model=SimulatorConversationsResponse)
async def list_simulator_conversations(
    ctx: TenantContext = Depends(require_role(UserRole.staff, UserRole.manager)),
    session: AsyncSession = Depends(get_async_session),
) -> SimulatorConversationsResponse:
    summaries = await SimulatorService.list_tenant_conversations(session, ctx.tenant_id)
    items = [
        SimulatorConversationItem(
            id=summary.id,
            client_name=summary.client_name,
            client_contact=summary.client_contact,
            status=summary.status.value,
            message_count=summary.message_count,
            updated_at=summary.updated_at,
        )
        for summary in summaries
    ]
    return SimulatorConversationsResponse(items=items, total=len(items))
