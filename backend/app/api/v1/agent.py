"""Focused agentic workflow — Phase B (dry-run endpoint).

Exposes the bounded Phase A agent through a single, safe endpoint. The endpoint
only returns a deterministic recommendation; it creates no task, no escalation,
no suggested reply, and sends nothing to the client. ``apply=true`` is rejected
(not yet enabled) so an apply request is never silently ignored.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, status
from fastapi.exceptions import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.core.tenant_context import TenantContext, require_role
from app.models.user import UserRole
from app.schemas.agent import AgentDecision, AgentRunRequest
from app.services.agent_orchestrator_service import AgentOrchestratorService
from app.services.conversation_service import ConversationService


router = APIRouter()


@router.post("/{conversation_id}/agent/run", response_model=AgentDecision)
async def run_agent(
    conversation_id: UUID,
    payload: AgentRunRequest,
    ctx: TenantContext = Depends(require_role(UserRole.staff, UserRole.manager)),
    session: AsyncSession = Depends(get_async_session),
) -> AgentDecision:
    if payload.apply:
        # Acting on a recommendation (creating task/escalation) is a later phase.
        # Reject explicitly rather than silently performing a dry-run.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "detail": "agent apply is not enabled yet",
                "error_code": "agent_apply_not_enabled",
            },
        )

    _, message = await ConversationService(session).get_tenant_inbound_message_or_error(
        conversation_id,
        payload.message_id,
        ctx,
    )

    decision = AgentOrchestratorService(session).run(message=message, ctx=ctx)
    await session.commit()
    return decision
