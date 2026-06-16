"""Focused bounded tool-using agent orchestrator."""
from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant_context import TenantContext
from app.models.conversation import Conversation
from app.models.message import Message
from app.repositories.escalation_repository import EscalationRepository
from app.repositories.task_repository import TaskRepository
from app.schemas.agent import (
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    SKIPPED_REASON_NOT_TRIGGER,
    AgentApplied,
    AgentDecision,
    AgentRunResponse,
    AgentToolTrace,
    RecommendedEscalation,
    RecommendedTask,
)
from app.schemas.escalation import EscalationCreate
from app.schemas.task import TaskCreate
from app.services.agent.planner import (
    AGENT_MAX_TOOL_CALLS,
    AGENT_TRIGGER_INTENTS,
    INTENT_CANCELLATION_REQUEST,
    INTENT_COMPLAINT,
    INTENT_GUEST_COUNT_CHANGE,
    INTENT_HUMAN_ESCALATION,
    INTENT_PAYMENT_ISSUE,
    INTENT_URGENT_CHANGE,
    KNOWN_RISK_LEVELS,
    decide_escalation,
    decide_task,
    plan_tools,
    should_run_intent,
    tool_plan_exceeds_max,
    trim_plan_safely,
)
from app.services.agent.tool_registry import AgentToolRegistry, create_default_tool_registry
from app.services.agent.tool_types import (
    AGENT_SOURCE_TYPE,
    MODE_APPLY,
    MODE_DRY_RUN,
    STATUS_PLANNED,
    AgentToolContext,
    escalation_summary,
    task_description,
    task_title,
)
from app.services.audit_log_service import (
    AUDIT_EVENT_AGENT_COMPLETED,
    AUDIT_EVENT_AGENT_DECISION_CREATED,
    AUDIT_EVENT_AGENT_HUMAN_REVIEW_REQUIRED,
    AUDIT_EVENT_AGENT_SKIPPED,
    AUDIT_EVENT_AGENT_STARTED,
    AUDIT_EVENT_AGENT_TOOL_EXECUTED,
    AUDIT_EVENT_AGENT_TOOL_FAILED,
    AUDIT_EVENT_AGENT_TOOL_PLANNED,
    AuditLogService,
)
from app.services.escalation_service import EscalationService
from app.services.risk_detection_service import RISK_LEVEL_HIGH
from app.services.task_service import TaskService


class AgentOrchestratorService:
    def __init__(
        self,
        session: AsyncSession | None = None,
        tool_registry: AgentToolRegistry | None = None,
    ) -> None:
        self.session = session
        self.tool_registry = tool_registry or create_default_tool_registry()

    @staticmethod
    def should_run(message: Message) -> bool:
        """Trigger gate: the agent runs only for risky/complex intents."""
        return should_run_intent(message.intent_label)

    def decide(self, message: Message) -> AgentDecision:
        """Compute the bounded, deterministic recommendation. Pure, no writes."""
        audit_run_id = uuid4()
        intent = message.intent_label

        if not self.should_run(message):
            return AgentDecision(
                ran=False,
                skipped_reason=SKIPPED_REASON_NOT_TRIGGER,
                trigger_intent=None,
                risk_level=message.risk_level,
                risk_reason=message.risk_reason,
                recommended_task=RecommendedTask(should_create=False, reason="skipped"),
                recommended_escalation=RecommendedEscalation(
                    should_escalate=False, reason="skipped"
                ),
                human_review_required=False,
                confidence=CONFIDENCE_HIGH,
                audit_run_id=audit_run_id,
            )

        risk_level = message.risk_level
        risk_known = risk_level in KNOWN_RISK_LEVELS
        is_high_risk = risk_level == RISK_LEVEL_HIGH
        planned_tools = plan_tools(
            intent,
            is_high_risk=is_high_risk,
            message_body=message.body or "",
        )

        return AgentDecision(
            ran=True,
            skipped_reason=None,
            trigger_intent=intent,
            risk_level=risk_level,
            risk_reason=message.risk_reason,
            recommended_task=decide_task(intent),
            recommended_escalation=decide_escalation(intent, is_high_risk=is_high_risk),
            human_review_required=not risk_known,
            confidence=CONFIDENCE_HIGH if risk_known else CONFIDENCE_LOW,
            audit_run_id=audit_run_id,
            tools_used=[
                AgentToolTrace(
                    tool_name=tool.name,
                    status=STATUS_PLANNED,
                    mode=MODE_DRY_RUN,
                    summary=f"Planned {tool.name}.",
                )
                for tool in planned_tools
            ],
        )

    def run(self, *, message: Message, ctx: TenantContext) -> AgentDecision:
        """Decide and optionally write the legacy decision audit event."""
        decision = self.decide(message)
        if self.session is not None:
            self._audit(decision, message, ctx)
        return decision

    async def run_tool_agent(
        self,
        *,
        conversation: Conversation,
        message: Message,
        ctx: TenantContext,
        apply: bool = False,
    ) -> AgentRunResponse:
        """Run the bounded tool plan once and return a visible tool trace."""
        if self.session is None:
            raise RuntimeError("run_tool_agent requires a database session")

        decision = self.decide(message)
        mode = MODE_APPLY if apply else MODE_DRY_RUN

        if not decision.ran:
            self._audit(decision, message, ctx)
            return AgentRunResponse(
                **decision.model_dump(exclude={"tools_used"}),
                message_id=message.id,
                conversation_id=conversation.id,
                intent_label=message.intent_label,
                tools_used=[],
                applied=AgentApplied() if apply else None,
            )

        plan = plan_tools(
            message.intent_label,
            is_high_risk=message.risk_level == RISK_LEVEL_HIGH,
            message_body=message.body or "",
        )
        if tool_plan_exceeds_max(
            message.intent_label,
            is_high_risk=message.risk_level == RISK_LEVEL_HIGH,
            message_body=message.body or "",
        ):
            decision.human_review_required = True
            decision.confidence = CONFIDENCE_LOW

        self._audit_agent_event(
            AUDIT_EVENT_AGENT_STARTED,
            ctx=ctx,
            message=message,
            audit_run_id=decision.audit_run_id,
            details={"apply": apply, "max_tool_calls": AGENT_MAX_TOOL_CALLS},
        )
        for item in plan:
            self._audit_agent_event(
                AUDIT_EVENT_AGENT_TOOL_PLANNED,
                ctx=ctx,
                message=message,
                audit_run_id=decision.audit_run_id,
                details={"tool_name": item.name, "mode": mode},
            )

        applied = AgentApplied() if apply else None
        traces: list[AgentToolTrace] = []
        tool_context = AgentToolContext(
            session=self.session,
            conversation=conversation,
            message=message,
            tenant_context=ctx,
            decision=decision,
            applied=applied,
        )

        for item in plan:
            try:
                result = await self.tool_registry.get_tool(item.name).run(tool_context, mode)
                traces.append(result.trace)
                if result.rag_result is not None:
                    tool_context.rag_result = result.rag_result
                if result.suggested_text is not None:
                    tool_context.suggested_text = result.suggested_text
                if result.human_review_required:
                    decision.human_review_required = True
                if result.confidence is not None:
                    decision.confidence = result.confidence
                for event in result.audit_events:
                    self._audit_agent_event(
                        event.event_type,
                        ctx=ctx,
                        message=message,
                        audit_run_id=decision.audit_run_id,
                        resource_type=event.resource_type,
                        resource_id=event.resource_id,
                        details=event.details,
                    )
                self._audit_agent_event(
                    AUDIT_EVENT_AGENT_TOOL_EXECUTED,
                    ctx=ctx,
                    message=message,
                    audit_run_id=decision.audit_run_id,
                    resource_id=result.trace.created_id,
                    details={
                        "tool_name": result.trace.tool_name,
                        "status": result.trace.status,
                        "mode": result.trace.mode,
                        "source_count": len(result.trace.source_ids),
                    },
                )
            except Exception:
                self._audit_agent_event(
                    AUDIT_EVENT_AGENT_TOOL_FAILED,
                    ctx=ctx,
                    message=message,
                    audit_run_id=decision.audit_run_id,
                    details={"tool_name": item.name, "mode": mode},
                )
                raise

        decision.tools_used = traces
        if decision.human_review_required:
            self._audit_agent_event(
                AUDIT_EVENT_AGENT_HUMAN_REVIEW_REQUIRED,
                ctx=ctx,
                message=message,
                audit_run_id=decision.audit_run_id,
                details={"reason": "agent_tool_fallback_or_unclear_risk"},
            )
        self._audit(decision, message, ctx)
        self._audit_agent_event(
            AUDIT_EVENT_AGENT_COMPLETED,
            ctx=ctx,
            message=message,
            audit_run_id=decision.audit_run_id,
            details={"tool_count": len(traces), "apply": apply},
        )

        return AgentRunResponse(
            **decision.model_dump(exclude={"tools_used"}),
            message_id=message.id,
            conversation_id=conversation.id,
            intent_label=message.intent_label,
            tools_used=traces,
            applied=applied,
        )

    async def apply_decision(
        self,
        *,
        decision: AgentDecision,
        conversation_id: UUID,
        message: Message,
        ctx: TenantContext,
    ) -> AgentApplied:
        """Legacy compatibility path for older callers that apply pure decisions.

        New endpoint flow uses ``run_tool_agent()``, where creation is handled by
        concrete agent tools. Keep this small path stable for existing imports.
        """
        applied = AgentApplied()
        if not decision.ran:
            return applied
        if self.session is None:
            raise RuntimeError("apply_decision requires a database session")

        if decision.recommended_task.should_create:
            existing_task = await TaskRepository(self.session).find_by_source(
                ctx.tenant_id,
                source_type=AGENT_SOURCE_TYPE,
                source_message_id=message.id,
            )
            if existing_task is not None:
                applied.task_id = existing_task.id
            else:
                task = await TaskService(self.session).create_task(
                    TaskCreate(
                        conversation_id=conversation_id,
                        message_id=message.id,
                        title=task_title(decision),
                        description=task_description(decision, message),
                        assigned_to_user_id=ctx.user_id,
                    ),
                    ctx,
                    source_type=AGENT_SOURCE_TYPE,
                    source_message_id=message.id,
                )
                applied.task_id = task.id

        if decision.recommended_escalation.should_escalate:
            existing_escalation = await EscalationRepository(self.session).find_by_source(
                ctx.tenant_id,
                source_type=AGENT_SOURCE_TYPE,
                source_message_id=message.id,
            )
            if existing_escalation is not None:
                applied.escalation_id = existing_escalation.id
            else:
                escalation = await EscalationService(self.session).create_escalation(
                    EscalationCreate(
                        conversation_id=conversation_id,
                        message_id=message.id,
                        ai_summary=escalation_summary(decision, message),
                        suggested_next_step="Manager review recommended by the focused agent.",
                    ),
                    ctx,
                    source_type=AGENT_SOURCE_TYPE,
                    source_message_id=message.id,
                )
                applied.escalation_id = escalation.id

        return applied

    @staticmethod
    def _plan_tools(intent: str | None, is_high_risk: bool, message_body: str) -> list[str]:
        return [
            item.name
            for item in plan_tools(
                intent,
                is_high_risk=is_high_risk,
                message_body=message_body,
            )
        ]

    @staticmethod
    def _trim_plan_safely(plan: list[str]) -> list[str]:
        return trim_plan_safely(plan)

    @staticmethod
    def _decide_task(intent: str | None) -> RecommendedTask:
        return decide_task(intent)

    @staticmethod
    def _decide_escalation(intent: str | None, is_high_risk: bool) -> RecommendedEscalation:
        return decide_escalation(intent, is_high_risk=is_high_risk)

    def _audit(self, decision: AgentDecision, message: Message, ctx: TenantContext) -> None:
        event_type = (
            AUDIT_EVENT_AGENT_DECISION_CREATED if decision.ran else AUDIT_EVENT_AGENT_SKIPPED
        )
        AuditLogService.record(
            self.session,
            tenant_id=ctx.tenant_id,
            event_type=event_type,
            actor_user_id=ctx.user_id,
            resource_type="message",
            resource_id=message.id,
            details={
                "audit_run_id": decision.audit_run_id,
                "ran": decision.ran,
                "skipped_reason": decision.skipped_reason,
                "trigger_intent": decision.trigger_intent,
                "risk_level": decision.risk_level,
                "recommended_task": decision.recommended_task.should_create,
                "recommended_escalation": decision.recommended_escalation.should_escalate,
                "human_review_required": decision.human_review_required,
                "confidence": decision.confidence,
            },
        )

    def _audit_agent_event(
        self,
        event_type: str,
        *,
        ctx: TenantContext,
        message: Message,
        audit_run_id: UUID,
        resource_type: str = "message",
        resource_id: UUID | str | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        AuditLogService.record(
            self.session,
            tenant_id=ctx.tenant_id,
            actor_user_id=ctx.user_id,
            event_type=event_type,
            resource_type=resource_type,
            resource_id=resource_id or message.id,
            details={
                "audit_run_id": audit_run_id,
                "message_id": message.id,
                "intent_label": message.intent_label,
                "risk_level": message.risk_level,
                **(details or {}),
            },
        )


__all__ = [
    "AGENT_MAX_TOOL_CALLS",
    "AGENT_SOURCE_TYPE",
    "AGENT_TRIGGER_INTENTS",
    "INTENT_CANCELLATION_REQUEST",
    "INTENT_COMPLAINT",
    "INTENT_GUEST_COUNT_CHANGE",
    "INTENT_HUMAN_ESCALATION",
    "INTENT_PAYMENT_ISSUE",
    "INTENT_URGENT_CHANGE",
    "AgentOrchestratorService",
]
