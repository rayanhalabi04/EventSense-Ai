from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.core.tenant_context import TenantContext, require_role
from app.models.conversation import Conversation
from app.models.user import UserRole
from app.schemas.conversation import (
    ConversationCreate,
    ConversationDetailResponse,
    ConversationRead,
    ConversationUpdate,
)
from app.models.suggested_reply import SuggestedReply
from app.schemas.suggested_reply import SuggestedReplyGenerateRequest, SuggestedReplyRead
from app.services.conversation_service import ConversationService


router = APIRouter()


async def get_tenant_conversation_or_403(
    conversation_id: UUID,
    ctx: TenantContext,
    session: AsyncSession,
) -> Conversation:
    return await ConversationService(session).get_tenant_conversation_or_403(conversation_id, ctx)


@router.post("", response_model=ConversationRead, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    payload: ConversationCreate,
    ctx: TenantContext = Depends(require_role(UserRole.staff, UserRole.manager)),
    session: AsyncSession = Depends(get_async_session),
) -> Conversation:
    return await ConversationService(session).create_conversation(payload, ctx)


@router.get("", response_model=list[ConversationRead])
async def list_conversations(
    ctx: TenantContext = Depends(require_role(UserRole.staff, UserRole.manager)),
    session: AsyncSession = Depends(get_async_session),
) -> list[Conversation]:
    return await ConversationService(session).list_conversations(ctx)


@router.patch("/{conversation_id}", response_model=ConversationRead)
async def update_conversation(
    conversation_id: UUID,
    payload: ConversationUpdate,
    ctx: TenantContext = Depends(require_role(UserRole.staff, UserRole.manager)),
    session: AsyncSession = Depends(get_async_session),
) -> Conversation:
    return await ConversationService(session).update_conversation(conversation_id, payload, ctx)


@router.get("/{conversation_id}/detail", response_model=ConversationDetailResponse)
async def get_conversation_detail(
    conversation_id: UUID,
    ctx: TenantContext = Depends(require_role(UserRole.staff, UserRole.manager)),
    session: AsyncSession = Depends(get_async_session),
) -> ConversationDetailResponse:
    return await ConversationService(session).get_conversation_detail(conversation_id, ctx)


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
    requested_message_id = payload.message_id if payload is not None else None
    return await ConversationService(session).create_suggested_reply(
        conversation_id,
        requested_message_id,
        ctx,
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
    return await ConversationService(session).list_suggested_replies(conversation_id, ctx)


@router.get("/{conversation_id}", response_model=ConversationRead)
async def get_conversation(
    conversation_id: UUID,
    ctx: TenantContext = Depends(require_role(UserRole.staff, UserRole.manager)),
    session: AsyncSession = Depends(get_async_session),
) -> Conversation:
    return await get_tenant_conversation_or_403(conversation_id, ctx, session)
