"""Shared types for the bounded EventSense agent tools."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant_context import TenantContext
from app.models.conversation import Conversation
from app.models.message import Message
from app.schemas.agent import AgentApplied, AgentDecision, AgentToolTrace
from app.services.rag_service import RagResult


AgentToolName = str
AgentToolMode = str
AgentToolStatus = str

TOOL_RAG_SEARCH = "rag_search"
TOOL_SUGGEST_REPLY = "suggest_reply"
TOOL_CREATE_FOLLOW_UP_TASK = "create_follow_up_task"
TOOL_ESCALATE_TO_MANAGER = "escalate_to_manager"

MODE_DRY_RUN = "dry_run"
MODE_APPLY = "apply"

STATUS_SUCCESS = "success"
STATUS_RECOMMENDED = "recommended"
STATUS_UNSUPPORTED = "unsupported"
STATUS_DRAFT = "draft"
STATUS_FAILED = "failed"
STATUS_PLANNED = "planned"

# Provenance marker stamped on agent-created records.
AGENT_SOURCE_TYPE = "agent"


@dataclass(frozen=True)
class AgentToolPlanItem:
    name: AgentToolName


@dataclass(frozen=True)
class AgentToolAuditEvent:
    event_type: str
    resource_type: str = "message"
    resource_id: UUID | str | None = None
    details: dict[str, object] = field(default_factory=dict)


@dataclass
class AgentToolContext:
    session: AsyncSession
    conversation: Conversation
    message: Message
    tenant_context: TenantContext
    decision: AgentDecision
    applied: AgentApplied | None = None
    rag_result: RagResult | None = None
    suggested_text: str | None = None


@dataclass
class AgentToolResult:
    trace: AgentToolTrace
    rag_result: RagResult | None = None
    suggested_text: str | None = None
    human_review_required: bool = False
    confidence: str | None = None
    audit_events: list[AgentToolAuditEvent] = field(default_factory=list)


class BaseAgentTool(Protocol):
    name: AgentToolName
    description: str

    async def run(
        self,
        context: AgentToolContext,
        mode: AgentToolMode,
    ) -> AgentToolResult:
        ...


def input_summary(message: Message) -> str:
    body = (message.body or "").strip().replace("\n", " ")
    if len(body) > 80:
        return f"{body[:77]}..."
    return body or "No message body"


def readable_intent(decision: AgentDecision) -> str:
    return (decision.trigger_intent or "message").replace("_", " ")


def task_title(decision: AgentDecision) -> str:
    intent = readable_intent(decision)
    if decision.risk_level:
        return f"Agent follow-up: {intent} ({decision.risk_level} risk)"
    return f"Agent follow-up: {intent}"


def task_description(decision: AgentDecision, message: Message) -> str:
    intent = readable_intent(decision)
    parts = [f"Created by the focused agent for a {intent} message."]
    if message.body:
        parts.append(f"Client message: {message.body}")
    if decision.risk_reason:
        parts.append(f"Risk ({decision.risk_level or 'unknown'}): {decision.risk_reason}")
    parts.append("This is an agent recommendation - review before acting.")
    return "\n\n".join(parts)


def escalation_summary(decision: AgentDecision, message: Message) -> str:
    intent = readable_intent(decision)
    summary = f"Agent flagged a {intent} message"
    if decision.risk_level:
        summary += f" at {decision.risk_level} risk"
    summary += "."
    reason = decision.recommended_escalation.reason
    if reason:
        summary += f" Reason: {reason.replace('_', ' ')}."
    return summary
