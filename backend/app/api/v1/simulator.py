from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.conversations import get_tenant_conversation_or_403
from app.core.database import get_async_session
from app.core.tenant_context import TenantContext, get_current_tenant_context
from app.models.conversation import Conversation
from app.models.message import Message, MessageDirection
from app.schemas.simulator import SimulatedWhatsAppMessageCreate, SimulatedWhatsAppMessageRead


router = APIRouter()

WHATSAPP_SIMULATOR_SOURCE = "whatsapp_simulator"


@router.post("/messages", response_model=SimulatedWhatsAppMessageRead, status_code=status.HTTP_201_CREATED)
async def simulate_whatsapp_message(
    payload: SimulatedWhatsAppMessageCreate,
    ctx: TenantContext = Depends(get_current_tenant_context),
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Conversation | Message]:
    if payload.conversation_id is not None:
        conversation = await get_tenant_conversation_or_403(payload.conversation_id, ctx, session)
    else:
        if not payload.client_name:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="client_name is required when conversation_id is not provided",
            )
        conversation = Conversation(
            tenant_id=ctx.tenant_id,
            client_name=payload.client_name,
            client_contact=payload.client_contact,
        )
        session.add(conversation)
        await session.flush()

    message = Message(
        tenant_id=ctx.tenant_id,
        conversation_id=conversation.id,
        direction=MessageDirection.inbound,
        body=payload.body,
        source=WHATSAPP_SIMULATOR_SOURCE,
        sender_user_id=None,
    )
    session.add(message)
    await session.commit()
    await session.refresh(conversation)
    await session.refresh(message)
    return {"conversation": conversation, "message": message}
