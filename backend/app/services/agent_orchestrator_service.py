"""Focused agentic workflow — Phase A (bounded, dry-run recommendations).

This service exists to prove the agent does **not** run freely:

- It runs only for a fixed set of risky/complex trigger intents; every other
  intent is skipped with a reason and produces no recommendation to act.
- It is bounded: a single, fixed, branch-free decision is computed once. There
  is no loop, no model-driven tool selection, and no recursion.
- It is deterministic: decisions are rules over the message's already-computed
  ``intent_label`` and ``risk_level`` fields. No RAG, no LLM, no I/O.
- It performs **no writes**. It creates no task and no escalation; it only
  returns an ``AgentDecision`` recommendation. The optional audit record is the
  sole side effect, and only when a session is supplied.
- ``tenant_id`` is never accepted as input. The only tenant identity comes from
  the JWT-derived :class:`TenantContext` passed to :meth:`run`, used purely to
  stamp the audit record.
"""
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant_context import TenantContext
from app.models.message import Message
from app.schemas.agent import (
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    SKIPPED_REASON_NOT_TRIGGER,
    AgentDecision,
    RecommendedEscalation,
    RecommendedTask,
)
from app.services.audit_log_service import (
    AUDIT_EVENT_AGENT_DECISION_CREATED,
    AUDIT_EVENT_AGENT_SKIPPED,
    AuditLogService,
)
from app.services.risk_detection_service import (
    RISK_LEVEL_HIGH,
    RISK_LEVEL_LOW,
    RISK_LEVEL_MEDIUM,
)


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
