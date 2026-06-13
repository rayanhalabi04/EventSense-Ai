"""Manager escalation agent tool."""
from __future__ import annotations

from app.repositories.escalation_repository import EscalationRepository
from app.schemas.agent import AgentToolTrace
from app.schemas.escalation import EscalationCreate
from app.services.agent.tool_types import (
    AGENT_SOURCE_TYPE,
    MODE_DRY_RUN,
    STATUS_RECOMMENDED,
    STATUS_SUCCESS,
    TOOL_ESCALATE_TO_MANAGER,
    AgentToolAuditEvent,
    AgentToolContext,
    AgentToolMode,
    AgentToolResult,
    BaseAgentTool,
    escalation_summary,
    input_summary,
    readable_intent,
)
from app.services.audit_log_service import AUDIT_EVENT_AGENT_ESCALATION_CREATED
from app.services.escalation_service import EscalationService


class EscalateToManagerTool(BaseAgentTool):
    name = TOOL_ESCALATE_TO_MANAGER
    description = "Recommend or create/reuse an idempotent manager escalation."

    async def run(
        self,
        context: AgentToolContext,
        mode: AgentToolMode,
    ) -> AgentToolResult:
        if mode == MODE_DRY_RUN:
            return AgentToolResult(
                trace=AgentToolTrace(
                    tool_name=TOOL_ESCALATE_TO_MANAGER,
                    status=STATUS_RECOMMENDED,
                    mode=mode,
                    summary=f"Recommended manager escalation for {readable_intent(context.decision)}.",
                    input_summary=input_summary(context.message),
                    output_summary=escalation_summary(context.decision, context.message),
                    recommended={
                        "ai_summary": escalation_summary(context.decision, context.message),
                        "suggested_next_step": "Manager review recommended by the focused agent.",
                    },
                )
            )

        existing_escalation = await EscalationRepository(context.session).find_by_source(
            context.tenant_context.tenant_id,
            source_type=AGENT_SOURCE_TYPE,
            source_message_id=context.message.id,
        )
        audit_events: list[AgentToolAuditEvent] = []
        if existing_escalation is not None:
            escalation_id = existing_escalation.id
        else:
            escalation = await EscalationService(context.session).create_escalation(
                EscalationCreate(
                    conversation_id=context.conversation.id,
                    message_id=context.message.id,
                    ai_summary=escalation_summary(context.decision, context.message),
                    suggested_next_step=(
                        "Manager review recommended by the focused agent."
                        if context.suggested_text is None
                        else "Review the draft reply and next operational step before contacting the client."
                    ),
                ),
                context.tenant_context,
                source_type=AGENT_SOURCE_TYPE,
                source_message_id=context.message.id,
            )
            escalation_id = escalation.id
            audit_events.append(
                AgentToolAuditEvent(
                    event_type=AUDIT_EVENT_AGENT_ESCALATION_CREATED,
                    resource_type="escalation",
                    resource_id=escalation.id,
                    details={"source_type": AGENT_SOURCE_TYPE},
                )
            )
        if context.applied is not None:
            context.applied.escalation_id = escalation_id
        return AgentToolResult(
            trace=AgentToolTrace(
                tool_name=TOOL_ESCALATE_TO_MANAGER,
                status=STATUS_SUCCESS,
                mode=mode,
                summary="Created or reused manager escalation.",
                input_summary=input_summary(context.message),
                output_summary=escalation_summary(context.decision, context.message),
                created_id=escalation_id,
            ),
            audit_events=audit_events,
        )
