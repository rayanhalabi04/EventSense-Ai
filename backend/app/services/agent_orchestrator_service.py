"""Compatibility wrapper for the focused bounded agent service.

New code should import from ``app.services.agent`` or
``app.services.agent.orchestrator``. This module remains so existing imports do
not break.
"""

from app.services.agent.orchestrator import (
    AGENT_MAX_TOOL_CALLS,
    AGENT_SOURCE_TYPE,
    AGENT_TRIGGER_INTENTS,
    INTENT_CANCELLATION_REQUEST,
    INTENT_COMPLAINT,
    INTENT_GUEST_COUNT_CHANGE,
    INTENT_HUMAN_ESCALATION,
    INTENT_PAYMENT_ISSUE,
    INTENT_URGENT_CHANGE,
    AgentOrchestratorService,
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
