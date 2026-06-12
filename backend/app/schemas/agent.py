"""Schemas for the focused agentic workflow (Phase A — dry-run only).

The agent never sends client messages, never creates tasks or escalations, and
never accepts a ``tenant_id`` from caller input. An ``AgentDecision`` is a
read-only *recommendation* object; acting on it is a deliberate, separate step
introduced in a later phase.
"""
from uuid import UUID

from pydantic import BaseModel, ConfigDict


CONFIDENCE_HIGH = "high"
CONFIDENCE_LOW = "low"

SKIPPED_REASON_NOT_TRIGGER = "intent_not_in_trigger_set"


class AgentRunRequest(BaseModel):
    """Body for ``POST .../agent/run``. ``tenant_id`` is intentionally absent and
    forbidden — tenant identity comes only from the JWT context."""

    message_id: UUID
    apply: bool = False

    # Reject any unexpected field (e.g. a smuggled ``tenant_id``) with a 422.
    model_config = ConfigDict(extra="forbid")


class RecommendedTask(BaseModel):
    """Whether a follow-up task *should* be created. No task is created here."""

    should_create: bool
    reason: str | None = None


class RecommendedEscalation(BaseModel):
    """Whether a manager escalation *should* happen. No escalation is created here."""

    should_escalate: bool
    reason: str | None = None


class AgentDecision(BaseModel):
    """Bounded, deterministic recommendation for a single message.

    This is the pure decision object. It carries no created-record ids — those
    live on ``AgentRunResponse.applied`` only when the caller asked to apply.
    """

    ran: bool
    skipped_reason: str | None = None
    trigger_intent: str | None = None
    risk_level: str | None = None
    risk_reason: str | None = None
    recommended_task: RecommendedTask
    recommended_escalation: RecommendedEscalation
    human_review_required: bool
    confidence: str
    audit_run_id: UUID


class AgentApplied(BaseModel):
    """Ids of records the agent created when ``apply=true``. Each is null when
    the decision did not recommend that record (or when ``apply=false``)."""

    task_id: UUID | None = None
    escalation_id: UUID | None = None


class AgentRunResponse(AgentDecision):
    """The decision plus, when ``apply=true``, the created record ids. For
    ``apply=false`` ``applied`` is null and no records exist."""

    applied: AgentApplied | None = None
