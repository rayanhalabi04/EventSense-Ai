"""Schemas for the focused bounded tool-using agent.

The agent never sends client messages and never accepts a ``tenant_id`` from
caller input. ``apply=false`` returns tool recommendations/previews only;
``apply=true`` persists allowed draft/task/escalation outputs.
"""
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


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


class AgentToolTrace(BaseModel):
    tool_name: str
    status: str
    mode: str
    summary: str
    input_summary: str | None = None
    output_summary: str | None = None
    source_ids: list[str] = Field(default_factory=list)
    suggested_reply_preview: str | None = None
    created_id: UUID | None = None
    recommended: dict[str, object] | None = None


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
    tools_used: list[AgentToolTrace] = Field(default_factory=list)


class AgentApplied(BaseModel):
    """Ids of records the agent created when ``apply=true``. Each is null when
    the decision did not recommend that record (or when ``apply=false``)."""

    task_id: UUID | None = None
    escalation_id: UUID | None = None
    suggested_reply_id: UUID | None = None


class AgentRunResponse(AgentDecision):
    """The decision plus visible tool trace and optional applied record ids."""

    message_id: UUID | None = None
    conversation_id: UUID | None = None
    intent_label: str | None = None
    tools_used: list[AgentToolTrace] = Field(default_factory=list)
    applied: AgentApplied | None = None
