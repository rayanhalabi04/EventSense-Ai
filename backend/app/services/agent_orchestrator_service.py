"""Focused agentic workflow — Phase A (bounded, dry-run recommendations).

This service exists to prove the agent does **not** run freely:

- It runs only for a fixed set of risky/complex trigger intents; every other
  intent is skipped with a reason and produces no recommendation to act.
- It is bounded: a single, fixed, branch-free decision is computed once. There
  is no loop, no model-driven tool selection, and no recursion.
- It is deterministic: decisions are rules over the message's already-computed
  ``intent_label`` and ``risk_level`` fields. No RAG, no LLM, no I/O.
- ``decide``/``run`` perform **no writes** beyond an optional audit record: they
  only return an ``AgentDecision`` recommendation. Creating records is a separate,
  explicit step (:meth:`apply_decision`) that the caller opts into with
  ``apply=true``; it reuses the existing Task/Escalation services (no duplicated
  validation, no new write logic here) and never sends a client message.
- ``tenant_id`` is never accepted as input. The only tenant identity comes from
  the JWT-derived :class:`TenantContext` passed to :meth:`run`/``apply_decision``.
"""
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant_context import TenantContext
from app.models.message import Message
from app.repositories.escalation_repository import EscalationRepository
from app.repositories.task_repository import TaskRepository
from app.schemas.agent import (
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    SKIPPED_REASON_NOT_TRIGGER,
    AgentApplied,
    AgentDecision,
    RecommendedEscalation,
    RecommendedTask,
)
from app.schemas.escalation import EscalationCreate
from app.schemas.task import TaskCreate
from app.services.audit_log_service import (
    AUDIT_EVENT_AGENT_DECISION_CREATED,
    AUDIT_EVENT_AGENT_SKIPPED,
    AuditLogService,
)
from app.services.escalation_service import EscalationService
from app.services.risk_detection_service import (
    RISK_LEVEL_HIGH,
    RISK_LEVEL_LOW,
    RISK_LEVEL_MEDIUM,
)
from app.services.task_service import TaskService


INTENT_COMPLAINT = "complaint"
INTENT_CANCELLATION_REQUEST = "cancellation_request"
INTENT_PAYMENT_ISSUE = "payment_issue"
INTENT_URGENT_CHANGE = "urgent_change"
INTENT_GUEST_COUNT_CHANGE = "guest_count_change"
INTENT_HUMAN_ESCALATION = "human_escalation"

# The only intents the agent is allowed to act on. Membership is the trigger gate.
AGENT_TRIGGER_INTENTS = frozenset(
    {
        INTENT_COMPLAINT,
        INTENT_CANCELLATION_REQUEST,
        INTENT_PAYMENT_ISSUE,
        INTENT_URGENT_CHANGE,
        INTENT_GUEST_COUNT_CHANGE,
        INTENT_HUMAN_ESCALATION,
    }
)

# A risk_level outside this set (including None) is treated as missing/unclear,
# which forces a human-review fallback.
_KNOWN_RISK_LEVELS = frozenset({RISK_LEVEL_LOW, RISK_LEVEL_MEDIUM, RISK_LEVEL_HIGH})

# Provenance marker stamped on agent-created tasks/escalations. The pair
# (tenant_id, source_type=agent, source_message_id) keeps ``apply`` idempotent.
AGENT_SOURCE_TYPE = "agent"


class AgentOrchestratorService:
    def __init__(self, session: AsyncSession | None = None) -> None:
        # Session is optional so the decision logic can be exercised purely.
        # When present, a single audit record is written (no commit here).
        self.session = session

    @staticmethod
    def should_run(message: Message) -> bool:
        """Trigger gate: the agent runs only for risky/complex intents."""
        return message.intent_label in AGENT_TRIGGER_INTENTS

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
        risk_known = risk_level in _KNOWN_RISK_LEVELS
        is_high_risk = risk_level == RISK_LEVEL_HIGH

        task = self._decide_task(intent)
        escalation = self._decide_escalation(intent, is_high_risk)

        return AgentDecision(
            ran=True,
            skipped_reason=None,
            trigger_intent=intent,
            risk_level=risk_level,
            risk_reason=message.risk_reason,
            recommended_task=task,
            recommended_escalation=escalation,
            # Missing/unclear risk → we are not confident enough to recommend
            # autonomously; a human must review.
            human_review_required=not risk_known,
            confidence=CONFIDENCE_HIGH if risk_known else CONFIDENCE_LOW,
            audit_run_id=audit_run_id,
        )

    def run(self, *, message: Message, ctx: TenantContext) -> AgentDecision:
        """Decide and (if a session was supplied) audit. Still performs no writes
        beyond the single audit record. ``ctx`` is the only source of tenant_id."""
        decision = self.decide(message)
        if self.session is not None:
            self._audit(decision, message, ctx)
        return decision

    async def apply_decision(
        self,
        *,
        decision: AgentDecision,
        conversation_id: UUID,
        message: Message,
        ctx: TenantContext,
    ) -> AgentApplied:
        """Create the records the decision recommends, via the existing services.

        Only acts on a decision that ``ran`` and recommends the record. Tenant /
        conversation / message ownership and auditing are all handled by
        ``TaskService.create_task`` / ``EscalationService.create_escalation`` —
        this method adds no validation or write logic of its own. It never sends
        a client message and never approves/sends a suggested reply.
        """
        applied = AgentApplied()
        if not decision.ran:
            return applied
        if self.session is None:
            raise RuntimeError("apply_decision requires a database session")

        if decision.recommended_task.should_create:
            # Idempotent: reuse an existing agent task for this message instead of
            # creating a duplicate. Human/UI tasks (source_type NULL) are ignored.
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
                        title=self._task_title(decision),
                        description=self._task_description(decision, message),
                        # Assign to the acting user (always in-tenant); the service
                        # validates this and falls back to unassigned if None.
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
                        # Manager assignment is optional; the service leaves the
                        # escalation in the unassigned manager queue.
                        ai_summary=self._escalation_summary(decision, message),
                        suggested_next_step="Manager review recommended by the focused agent.",
                    ),
                    ctx,
                    source_type=AGENT_SOURCE_TYPE,
                    source_message_id=message.id,
                )
                applied.escalation_id = escalation.id

        return applied

    @staticmethod
    def _readable_intent(decision: AgentDecision) -> str:
        return (decision.trigger_intent or "message").replace("_", " ")

    @staticmethod
    def _task_title(decision: AgentDecision) -> str:
        intent = AgentOrchestratorService._readable_intent(decision)
        if decision.risk_level:
            return f"Agent follow-up: {intent} ({decision.risk_level} risk)"
        return f"Agent follow-up: {intent}"

    @staticmethod
    def _task_description(decision: AgentDecision, message: Message) -> str:
        intent = AgentOrchestratorService._readable_intent(decision)
        parts = [f"Created by the focused agent for a {intent} message."]
        if message.body:
            parts.append(f"Client message: {message.body}")
        if decision.risk_reason:
            parts.append(f"Risk ({decision.risk_level or 'unknown'}): {decision.risk_reason}")
        parts.append("This is an agent recommendation — review before acting.")
        return "\n\n".join(parts)

    @staticmethod
    def _escalation_summary(decision: AgentDecision, message: Message) -> str:
        intent = AgentOrchestratorService._readable_intent(decision)
        summary = f"Agent flagged a {intent} message"
        if decision.risk_level:
            summary += f" at {decision.risk_level} risk"
        summary += "."
        reason = decision.recommended_escalation.reason
        if reason:
            summary += f" Reason: {reason.replace('_', ' ')}."
        return summary

    @staticmethod
    def _decide_task(intent: str) -> RecommendedTask:
        # payment_issue, guest_count_change, urgent_change → follow-up task.
        if intent == INTENT_URGENT_CHANGE:
            return RecommendedTask(should_create=True, reason="urgent_change_intent")
        if intent == INTENT_PAYMENT_ISSUE:
            return RecommendedTask(should_create=True, reason="payment_issue_intent")
        if intent == INTENT_GUEST_COUNT_CHANGE:
            return RecommendedTask(should_create=True, reason="guest_count_change_intent")
        return RecommendedTask(should_create=False, reason=None)

    @staticmethod
    def _decide_escalation(intent: str, is_high_risk: bool) -> RecommendedEscalation:
        # Fixed priority so the reason is deterministic when multiple rules apply.
        if intent == INTENT_HUMAN_ESCALATION:
            return RecommendedEscalation(should_escalate=True, reason="human_escalation_intent")
        if is_high_risk:
            return RecommendedEscalation(should_escalate=True, reason="high_risk")
        if intent == INTENT_COMPLAINT:
            return RecommendedEscalation(should_escalate=True, reason="complaint_intent")
        if intent == INTENT_CANCELLATION_REQUEST:
            return RecommendedEscalation(
                should_escalate=True, reason="cancellation_request_intent"
            )
        if intent == INTENT_URGENT_CHANGE:
            return RecommendedEscalation(should_escalate=True, reason="urgent_change_intent")
        return RecommendedEscalation(should_escalate=False, reason=None)

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
