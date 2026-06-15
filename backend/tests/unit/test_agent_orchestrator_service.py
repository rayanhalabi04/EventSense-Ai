"""Unit tests for the bounded tool-using agent orchestrator.

These prove the agent does not run freely, decisions/tool plans are
deterministic, and dry-run decisions remain recommendation-only.
"""
import importlib.util
import inspect
from uuid import uuid4

import pytest

import app.services.agent_orchestrator_service as agent_module
import app.services.agent.planner as planner_module
from app.core.tenant_context import TenantContext
from app.models.audit_log import AuditLog
from app.models.message import Message
from app.models.user import UserRole
from app.schemas.agent import SKIPPED_REASON_NOT_TRIGGER
from app.services.agent.planner import plan_tools
from app.services.agent.tool_registry import (
    AgentToolRegistry,
    EXPECTED_AGENT_TOOL_NAMES,
    UnapprovedAgentToolError,
    UnknownAgentToolError,
    create_default_tool_registry,
)
from app.services.agent_orchestrator_service import (
    AGENT_TRIGGER_INTENTS,
    AgentOrchestratorService,
)


TRIGGER_LABELS = [
    "complaint",
    "cancellation_request",
    "payment_issue",
    "urgent_change",
    "guest_count_change",
    "human_escalation",
]

NON_TRIGGER_LABELS = [
    "booking_inquiry",
    "pricing_request",
    "service_question",
    "other",
]


def _message(intent_label: str | None, risk_level: str | None = "medium") -> Message:
    return Message(
        intent_label=intent_label,
        risk_level=risk_level,
        risk_reason="test reason" if risk_level else None,
    )


class _FakeSession:
    """Minimal stand-in: AuditLogService.record only calls ``session.add``."""

    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, obj: object) -> None:
        self.added.append(obj)


class _UnapprovedTool:
    name = "send_client_message"
    description = "Unapproved outbound tool."

    async def run(self, context, mode):
        raise AssertionError("unapproved tool should never run")


# --- Trigger gate -----------------------------------------------------------


@pytest.mark.parametrize("label", TRIGGER_LABELS)
def test_all_trigger_labels_run(label: str) -> None:
    decision = AgentOrchestratorService().decide(_message(label, "high"))

    assert decision.ran is True
    assert decision.trigger_intent == label
    assert decision.skipped_reason is None


@pytest.mark.parametrize("label", NON_TRIGGER_LABELS)
def test_non_trigger_labels_are_skipped(label: str) -> None:
    decision = AgentOrchestratorService().decide(_message(label, "high"))

    assert decision.ran is False
    assert decision.skipped_reason == SKIPPED_REASON_NOT_TRIGGER
    assert decision.trigger_intent is None
    assert decision.recommended_task.should_create is False
    assert decision.recommended_escalation.should_escalate is False


def test_trigger_set_is_exactly_the_six_risky_intents() -> None:
    assert AGENT_TRIGGER_INTENTS == frozenset(TRIGGER_LABELS)


# --- Deterministic decision rules ------------------------------------------


def test_human_escalation_recommends_escalation() -> None:
    decision = AgentOrchestratorService().decide(_message("human_escalation", "medium"))

    assert decision.recommended_escalation.should_escalate is True


def test_urgent_change_recommends_task_without_escalation_when_not_high_risk() -> None:
    decision = AgentOrchestratorService().decide(_message("urgent_change", "medium"))

    assert decision.recommended_task.should_create is True
    assert decision.recommended_escalation.should_escalate is False


def test_payment_issue_recommends_task() -> None:
    decision = AgentOrchestratorService().decide(_message("payment_issue", "medium"))

    assert decision.recommended_task.should_create is True
    assert decision.recommended_escalation.should_escalate is False


def test_guest_count_change_recommends_task() -> None:
    decision = AgentOrchestratorService().decide(_message("guest_count_change", "medium"))

    assert decision.recommended_task.should_create is True


def test_complaint_recommends_escalation() -> None:
    decision = AgentOrchestratorService().decide(_message("complaint", "medium"))

    assert decision.recommended_escalation.should_escalate is True
    assert decision.recommended_task.should_create is True
    assert [tool.tool_name for tool in decision.tools_used] == [
        "rag_search",
        "suggest_reply",
        "create_follow_up_task",
        "escalate_to_manager",
    ]


def test_cancellation_plans_rag_reply_without_escalation_when_not_high_risk() -> None:
    decision = AgentOrchestratorService().decide(
        _message("cancellation_request", "medium")
    )

    assert [tool.tool_name for tool in decision.tools_used] == [
        "rag_search",
        "suggest_reply",
    ]


def test_max_tool_call_limit_trims_to_human_review_safe_tools(monkeypatch) -> None:
    monkeypatch.setattr(planner_module, "AGENT_MAX_TOOL_CALLS", 2)

    trimmed = AgentOrchestratorService._trim_plan_safely(
        ["rag_search", "suggest_reply", "create_follow_up_task", "escalate_to_manager"]
    )

    assert trimmed == ["rag_search", "suggest_reply"]


def test_tool_registry_contains_exact_agent_tools() -> None:
    registry = create_default_tool_registry()

    assert set(registry.list_tools()) == EXPECTED_AGENT_TOOL_NAMES


def test_tool_registry_rejects_unknown_tool() -> None:
    registry = create_default_tool_registry()

    with pytest.raises(UnknownAgentToolError, match="unknown agent tool"):
        registry.get_tool("send_client_message")


def test_tool_registry_rejects_unapproved_registered_tool() -> None:
    with pytest.raises(UnapprovedAgentToolError, match="unapproved agent tools"):
        AgentToolRegistry([_UnapprovedTool()])


def test_planner_rejects_unapproved_tool_names(monkeypatch) -> None:
    monkeypatch.setattr(planner_module, "_raw_tool_names", lambda *args, **kwargs: ["send_client_message"])

    with pytest.raises(ValueError, match="unapproved agent tools planned"):
        plan_tools("complaint", is_high_risk=False, message_body="hello")


@pytest.mark.parametrize(
    ("intent", "risk_level", "expected_tools"),
    [
        (
            "complaint",
            "medium",
            ["rag_search", "suggest_reply", "create_follow_up_task", "escalate_to_manager"],
        ),
        ("cancellation_request", "medium", ["rag_search", "suggest_reply"]),
        (
            "cancellation_request",
            "high",
            ["rag_search", "suggest_reply", "escalate_to_manager"],
        ),
        ("payment_issue", "medium", ["create_follow_up_task", "suggest_reply"]),
        (
            "payment_issue",
            "high",
            ["create_follow_up_task", "suggest_reply", "escalate_to_manager"],
        ),
        ("urgent_change", "medium", ["rag_search", "create_follow_up_task", "suggest_reply"]),
        (
            "guest_count_change",
            "high",
            ["rag_search", "create_follow_up_task", "suggest_reply", "escalate_to_manager"],
        ),
        ("human_escalation", "medium", ["escalate_to_manager"]),
    ],
)
def test_planner_returns_expected_tool_order(
    intent: str,
    risk_level: str,
    expected_tools: list[str],
) -> None:
    planned = plan_tools(
        intent,
        is_high_risk=risk_level == "high",
        message_body="I need help",
    )

    assert [item.name for item in planned] == expected_tools


def test_cancellation_request_avoids_escalation_when_not_high_risk() -> None:
    decision = AgentOrchestratorService().decide(_message("cancellation_request", "medium"))

    assert decision.recommended_escalation.should_escalate is False


def test_high_risk_cancellation_request_recommends_escalation() -> None:
    decision = AgentOrchestratorService().decide(_message("cancellation_request", "high"))

    assert decision.recommended_escalation.should_escalate is True


def test_high_risk_forces_escalation_even_for_task_intent() -> None:
    decision = AgentOrchestratorService().decide(_message("payment_issue", "high"))

    assert decision.recommended_task.should_create is True
    assert decision.recommended_escalation.should_escalate is True


@pytest.mark.parametrize("risk_level", [None, "", "unknown"])
def test_missing_or_unclear_risk_requires_human_review(risk_level) -> None:
    decision = AgentOrchestratorService().decide(_message("complaint", risk_level))

    assert decision.human_review_required is True
    assert decision.confidence == "low"


def test_known_risk_is_high_confidence_no_human_review() -> None:
    decision = AgentOrchestratorService().decide(_message("complaint", "medium"))

    assert decision.human_review_required is False
    assert decision.confidence == "high"


# --- No writes / no records created -----------------------------------------


def test_decision_object_has_no_created_record_references() -> None:
    decision = AgentOrchestratorService().decide(_message("complaint", "high"))

    # A pure decision creates nothing, so there is no id to expose.
    for forbidden in ("task_id", "escalation_id", "applied"):
        assert not hasattr(decision, forbidden)


def test_run_writes_only_an_audit_log_no_task_or_escalation() -> None:
    session = _FakeSession()
    ctx = TenantContext(user_id=uuid4(), tenant_id=uuid4(), role=UserRole.staff)

    AgentOrchestratorService(session).run(message=_message("complaint", "high"), ctx=ctx)

    assert len(session.added) == 1
    assert all(isinstance(obj, AuditLog) for obj in session.added)


def test_run_audits_decision_created_for_trigger() -> None:
    session = _FakeSession()
    ctx = TenantContext(user_id=uuid4(), tenant_id=uuid4(), role=UserRole.staff)

    AgentOrchestratorService(session).run(message=_message("complaint", "high"), ctx=ctx)

    assert session.added[0].event_type == "agent.decision_created"


def test_run_audits_skipped_for_non_trigger() -> None:
    session = _FakeSession()
    ctx = TenantContext(user_id=uuid4(), tenant_id=uuid4(), role=UserRole.staff)

    AgentOrchestratorService(session).run(message=_message("booking_inquiry", "high"), ctx=ctx)

    assert session.added[0].event_type == "agent.skipped"


def test_decide_without_session_performs_no_audit() -> None:
    # No session supplied → decide() must not require DB and must not error.
    decision = AgentOrchestratorService().decide(_message("complaint", "high"))
    assert decision.ran is True


# --- Tenant safety ----------------------------------------------------------


def test_no_method_accepts_tenant_id_from_input() -> None:
    for method in (AgentOrchestratorService.decide, AgentOrchestratorService.run):
        params = inspect.signature(method).parameters
        assert "tenant_id" not in params


def test_agent_endpoint_module_exists() -> None:
    # Phase B added the dry-run endpoint; the module is now present.
    assert importlib.util.find_spec("app.api.v1.agent") is not None
