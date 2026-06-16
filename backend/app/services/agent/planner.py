"""Deterministic planner for the bounded EventSense agent."""
from __future__ import annotations

import os

from app.schemas.agent import RecommendedEscalation, RecommendedTask
from app.services.agent.tool_types import (
    TOOL_CREATE_FOLLOW_UP_TASK,
    TOOL_ESCALATE_TO_MANAGER,
    TOOL_RAG_SEARCH,
    TOOL_SUGGEST_REPLY,
    AgentToolPlanItem,
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

KNOWN_RISK_LEVELS = frozenset({RISK_LEVEL_LOW, RISK_LEVEL_MEDIUM, RISK_LEVEL_HIGH})
AGENT_MAX_TOOL_CALLS = int(os.getenv("AGENT_MAX_TOOL_CALLS", "4"))

APPROVED_TOOL_NAMES = frozenset(
    {
        TOOL_RAG_SEARCH,
        TOOL_SUGGEST_REPLY,
        TOOL_CREATE_FOLLOW_UP_TASK,
        TOOL_ESCALATE_TO_MANAGER,
    }
)


def should_run_intent(intent: str | None) -> bool:
    return intent in AGENT_TRIGGER_INTENTS


def plan_tools(
    intent: str | None,
    *,
    is_high_risk: bool,
    message_body: str,
) -> list[AgentToolPlanItem]:
    raw_plan = _raw_tool_names(intent, is_high_risk=is_high_risk, message_body=message_body)
    unapproved_tools = sorted(set(raw_plan) - APPROVED_TOOL_NAMES)
    if unapproved_tools:
        raise ValueError(f"unapproved agent tools planned: {unapproved_tools}")
    if len(raw_plan) > AGENT_MAX_TOOL_CALLS:
        raw_plan = trim_plan_safely(raw_plan)
    return [AgentToolPlanItem(name=tool_name) for tool_name in raw_plan]


def tool_plan_exceeds_max(
    intent: str | None,
    *,
    is_high_risk: bool,
    message_body: str,
) -> bool:
    return (
        len(_raw_tool_names(intent, is_high_risk=is_high_risk, message_body=message_body))
        > AGENT_MAX_TOOL_CALLS
    )


def _raw_tool_names(intent: str | None, *, is_high_risk: bool, message_body: str) -> list[str]:
    if intent == INTENT_COMPLAINT:
        return [
            TOOL_RAG_SEARCH,
            TOOL_SUGGEST_REPLY,
            TOOL_CREATE_FOLLOW_UP_TASK,
            TOOL_ESCALATE_TO_MANAGER,
        ]
    if intent == INTENT_CANCELLATION_REQUEST:
        plan = [TOOL_RAG_SEARCH, TOOL_SUGGEST_REPLY]
        if is_high_risk:
            plan.append(TOOL_ESCALATE_TO_MANAGER)
        return plan
    if intent == INTENT_PAYMENT_ISSUE:
        plan = [TOOL_CREATE_FOLLOW_UP_TASK, TOOL_SUGGEST_REPLY]
        if is_high_risk:
            plan.append(TOOL_ESCALATE_TO_MANAGER)
        return plan
    if intent in {INTENT_URGENT_CHANGE, INTENT_GUEST_COUNT_CHANGE}:
        plan = [TOOL_RAG_SEARCH, TOOL_CREATE_FOLLOW_UP_TASK, TOOL_SUGGEST_REPLY]
        if is_high_risk:
            plan.append(TOOL_ESCALATE_TO_MANAGER)
        return plan
    if intent == INTENT_HUMAN_ESCALATION:
        return [TOOL_ESCALATE_TO_MANAGER]
    return []


def trim_plan_safely(plan: list[str]) -> list[str]:
    priority = [
        TOOL_RAG_SEARCH,
        TOOL_SUGGEST_REPLY,
        TOOL_ESCALATE_TO_MANAGER,
        TOOL_CREATE_FOLLOW_UP_TASK,
    ]
    trimmed: list[str] = []
    for tool_name in priority:
        if (
            tool_name in plan
            and tool_name in APPROVED_TOOL_NAMES
            and len(trimmed) < AGENT_MAX_TOOL_CALLS
        ):
            trimmed.append(tool_name)
    return trimmed


def decide_task(intent: str | None) -> RecommendedTask:
    if intent == INTENT_COMPLAINT:
        return RecommendedTask(should_create=True, reason="complaint_intent")
    if intent == INTENT_URGENT_CHANGE:
        return RecommendedTask(should_create=True, reason="urgent_change_intent")
    if intent == INTENT_PAYMENT_ISSUE:
        return RecommendedTask(should_create=True, reason="payment_issue_intent")
    if intent == INTENT_GUEST_COUNT_CHANGE:
        return RecommendedTask(should_create=True, reason="guest_count_change_intent")
    return RecommendedTask(should_create=False, reason=None)


def decide_escalation(intent: str | None, *, is_high_risk: bool) -> RecommendedEscalation:
    if intent == INTENT_HUMAN_ESCALATION:
        return RecommendedEscalation(should_escalate=True, reason="human_escalation_intent")
    if is_high_risk:
        return RecommendedEscalation(should_escalate=True, reason="high_risk")
    if intent == INTENT_COMPLAINT:
        return RecommendedEscalation(should_escalate=True, reason="complaint_intent")
    return RecommendedEscalation(should_escalate=False, reason=None)
