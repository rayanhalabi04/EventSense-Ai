"""Focused agentic workflow — agent run endpoint.

Exposes the bounded agent through a single, safe endpoint.

- ``apply=false`` (default): returns a deterministic recommendation only — no
  task, no escalation, no suggested reply, nothing sent to the client.
- ``apply=true``: runs the same decision and creates the recommended follow-up
  task and/or escalation through the existing Task/Escalation services, then
  returns the decision plus the created ids. Still sends nothing to the client
  and never approves/sends a suggested reply.

Tenant identity comes only from the JWT context; ownership of the conversation
and message is validated before anything runs.
"""
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.core.tenant_context import TenantContext, require_role
from app.models.user import UserRole
from app.schemas.agent import AgentApplied, AgentRunRequest, AgentRunResponse
from app.services.agent_orchestrator_service import AgentOrchestratorService
from app.services.conversation_service import ConversationService


router = APIRouter()


@router.post("/{conversation_id}/agent/run", response_model=AgentRunResponse)
async def run_agent(
    conversation_id: UUID,
    payload: AgentRunRequest,
    ctx: TenantContext = Depends(require_role(UserRole.staff, UserRole.manager)),
    session: AsyncSession = Depends(get_async_session),
) -> AgentRunResponse:
    _, message = await ConversationService(session).get_tenant_inbound_message_or_error(
        conversation_id,
        payload.message_id,
        ctx,
    )

    orchestrator = AgentOrchestratorService(session)
    decision = orchestrator.run(message=message, ctx=ctx)

    applied: AgentApplied | None = None
    if payload.apply:
        applied = await orchestrator.apply_decision(
            decision=decision,
            conversation_id=conversation_id,
            message=message,
            ctx=ctx,
        )

    await session.commit()
    return AgentRunResponse(**decision.model_dump(), applied=applied)
