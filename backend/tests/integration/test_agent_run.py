from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.escalation import Escalation
from app.models.audit_log import AuditLog
from app.models.message import Message, MessageDirection
from app.models.suggested_reply import SuggestedReply
from app.models.tenant import Tenant
from app.models.task import Task


pytestmark = pytest.mark.asyncio


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def login(
    client: AsyncClient,
    email: str = "admin@elegant-weddings.demo",
    password: str = "demo-password-1",
    tenant_slug: str = "elegant-weddings",
) -> str:
    response = await client.post(
        "/auth/token",
        json={"email": email, "password": password, "tenant_slug": tenant_slug},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


async def login_royal(client: AsyncClient) -> str:
    return await login(
        client,
        email="admin@royal-events.demo",
        password="demo-password-2",
        tenant_slug="royal-events-agency",
    )


async def create_conversation(client: AsyncClient, token: str, client_name: str = "Agent Client") -> dict:
    response = await client.post(
        "/api/v1/conversations",
        headers=auth_headers(token),
        json={"client_name": client_name, "client_contact": "+96170000000"},
    )
    assert response.status_code == 201
    return response.json()


async def seed_inbound_message(
    db_session: AsyncSession,
    *,
    tenant: Tenant,
    conversation_id: str,
    body: str = "I want to complain about your service.",
    intent_label: str | None = "complaint",
    risk_level: str | None = "high",
) -> Message:
    """Seed a pre-classified inbound message directly — the message API does not
    classify, so intent/risk must be set explicitly for the agent to trigger."""
    message = Message(
        tenant_id=tenant.id,
        conversation_id=UUID(str(conversation_id)),
        direction=MessageDirection.inbound,
        body=body,
        intent_label=intent_label,
        risk_level=risk_level,
        risk_reason="seeded for test" if risk_level else None,
    )
    db_session.add(message)
    await db_session.commit()
    await db_session.refresh(message)
    return message


async def run_agent(
    client: AsyncClient,
    token: str,
    conversation_id: str,
    message_id: str,
    apply: bool = False,
):
    return await client.post(
        f"/api/v1/conversations/{conversation_id}/agent/run",
        headers=auth_headers(token),
        json={"message_id": message_id, "apply": apply},
    )


async def test_dry_run_returns_recommendation_for_risky_message(
    client: AsyncClient,
    db_session: AsyncSession,
    demo_tenants: dict[str, Tenant],
) -> None:
    token = await login(client)
    conversation = await create_conversation(client, token)
    message = await seed_inbound_message(
        db_session,
        tenant=demo_tenants["elegant-weddings"],
        conversation_id=conversation["id"],
    )

    response = await run_agent(client, token, conversation["id"], str(message.id))

    assert response.status_code == 200
    body = response.json()
    assert body["ran"] is True
    assert body["trigger_intent"] == "complaint"
    assert body["recommended_escalation"]["should_escalate"] is True


async def test_non_trigger_message_is_skipped(
    client: AsyncClient,
    db_session: AsyncSession,
    demo_tenants: dict[str, Tenant],
) -> None:
    token = await login(client)
    conversation = await create_conversation(client, token)
    message = await seed_inbound_message(
        db_session,
        tenant=demo_tenants["elegant-weddings"],
        conversation_id=conversation["id"],
        body="Do you have availability in June?",
        intent_label="booking_inquiry",
        risk_level="low",
    )

    response = await run_agent(client, token, conversation["id"], str(message.id))

    assert response.status_code == 200
    body = response.json()
    assert body["ran"] is False
    assert body["skipped_reason"] == "intent_not_in_trigger_set"


async def test_cross_tenant_conversation_is_forbidden(
    client: AsyncClient,
    db_session: AsyncSession,
    demo_tenants: dict[str, Tenant],
) -> None:
    owner_token = await login(client)
    conversation = await create_conversation(client, owner_token)
    message = await seed_inbound_message(
        db_session,
        tenant=demo_tenants["elegant-weddings"],
        conversation_id=conversation["id"],
    )

    intruder_token = await login_royal(client)
    response = await run_agent(client, intruder_token, conversation["id"], str(message.id))

    assert response.status_code == 403


async def test_message_not_in_conversation_is_rejected(
    client: AsyncClient,
    db_session: AsyncSession,
    demo_tenants: dict[str, Tenant],
) -> None:
    token = await login(client)
    conversation_x = await create_conversation(client, token, "Conv X")
    conversation_y = await create_conversation(client, token, "Conv Y")
    message = await seed_inbound_message(
        db_session,
        tenant=demo_tenants["elegant-weddings"],
        conversation_id=conversation_x["id"],
    )

    response = await run_agent(client, token, conversation_y["id"], str(message.id))

    assert response.status_code == 400


async def test_dry_run_creates_no_task_or_escalation_but_audits(
    client: AsyncClient,
    db_session: AsyncSession,
    demo_tenants: dict[str, Tenant],
) -> None:
    token = await login(client)
    conversation = await create_conversation(client, token)
    message = await seed_inbound_message(
        db_session,
        tenant=demo_tenants["elegant-weddings"],
        conversation_id=conversation["id"],
    )

    response = await run_agent(client, token, conversation["id"], str(message.id))
    assert response.status_code == 200

    conv_id = UUID(conversation["id"])
    tasks = (
        await db_session.execute(
            select(Task).where(Task.conversation_id == conv_id)
        )
    ).scalars().all()
    escalations = (
        await db_session.execute(
            select(Escalation).where(Escalation.conversation_id == conv_id)
        )
    ).scalars().all()
    assert tasks == []
    assert escalations == []

    audit_events = (
        await db_session.execute(
            select(AuditLog).where(AuditLog.event_type == "agent.decision_created")
        )
    ).scalars().all()
    assert len(audit_events) == 1


async def _tasks_for(db_session: AsyncSession, conversation_id: str) -> list[Task]:
    result = await db_session.execute(
        select(Task).where(Task.conversation_id == UUID(conversation_id))
    )
    return list(result.scalars().all())


async def _escalations_for(db_session: AsyncSession, conversation_id: str) -> list[Escalation]:
    result = await db_session.execute(
        select(Escalation).where(Escalation.conversation_id == UUID(conversation_id))
    )
    return list(result.scalars().all())


async def test_apply_true_payment_issue_creates_task_only(
    client: AsyncClient,
    db_session: AsyncSession,
    demo_tenants: dict[str, Tenant],
) -> None:
    tenant = demo_tenants["elegant-weddings"]
    token = await login(client)
    conversation = await create_conversation(client, token)
    message = await seed_inbound_message(
        db_session,
        tenant=tenant,
        conversation_id=conversation["id"],
        body="I was charged twice and my payment is unconfirmed.",
        intent_label="payment_issue",
        risk_level="medium",
    )

    response = await run_agent(client, token, conversation["id"], str(message.id), apply=True)

    assert response.status_code == 200
    body = response.json()
    assert body["ran"] is True
    assert body["recommended_task"]["should_create"] is True
    assert body["recommended_escalation"]["should_escalate"] is False
    assert body["applied"]["task_id"] is not None
    assert body["applied"]["escalation_id"] is None

    tasks = await _tasks_for(db_session, conversation["id"])
    escalations = await _escalations_for(db_session, conversation["id"])
    assert len(tasks) == 1
    assert len(escalations) == 0
    # AC-9: created record belongs to the authenticated tenant.
    assert tasks[0].tenant_id == tenant.id
    assert str(tasks[0].id) == body["applied"]["task_id"]


async def test_apply_true_complaint_creates_escalation_only(
    client: AsyncClient,
    db_session: AsyncSession,
    demo_tenants: dict[str, Tenant],
) -> None:
    tenant = demo_tenants["elegant-weddings"]
    token = await login(client)
    conversation = await create_conversation(client, token)
    message = await seed_inbound_message(
        db_session,
        tenant=tenant,
        conversation_id=conversation["id"],
        body="This is unacceptable and I am very upset.",
        intent_label="complaint",
        risk_level="medium",
    )

    response = await run_agent(client, token, conversation["id"], str(message.id), apply=True)

    assert response.status_code == 200
    body = response.json()
    assert body["recommended_task"]["should_create"] is False
    assert body["recommended_escalation"]["should_escalate"] is True
    assert body["applied"]["task_id"] is None
    assert body["applied"]["escalation_id"] is not None

    tasks = await _tasks_for(db_session, conversation["id"])
    escalations = await _escalations_for(db_session, conversation["id"])
    assert len(tasks) == 0
    assert len(escalations) == 1
    assert escalations[0].tenant_id == tenant.id
    # The escalation snapshots the message intent/risk via the existing service.
    assert escalations[0].intent_label == "complaint"
    assert str(escalations[0].id) == body["applied"]["escalation_id"]


async def test_apply_true_urgent_change_creates_task_and_escalation(
    client: AsyncClient,
    db_session: AsyncSession,
    demo_tenants: dict[str, Tenant],
) -> None:
    tenant = demo_tenants["elegant-weddings"]
    token = await login(client)
    conversation = await create_conversation(client, token)
    message = await seed_inbound_message(
        db_session,
        tenant=tenant,
        conversation_id=conversation["id"],
        body="We must move the ceremony to tomorrow morning, urgent.",
        intent_label="urgent_change",
        risk_level="medium",
    )

    response = await run_agent(client, token, conversation["id"], str(message.id), apply=True)

    assert response.status_code == 200
    body = response.json()
    assert body["applied"]["task_id"] is not None
    assert body["applied"]["escalation_id"] is not None

    tasks = await _tasks_for(db_session, conversation["id"])
    escalations = await _escalations_for(db_session, conversation["id"])
    assert len(tasks) == 1
    assert len(escalations) == 1

    # AC-10: creations are audited through the existing services.
    task_audit = (
        await db_session.execute(
            select(AuditLog).where(AuditLog.event_type == "task.created")
        )
    ).scalars().all()
    esc_audit = (
        await db_session.execute(
            select(AuditLog).where(AuditLog.event_type == "escalation.created")
        )
    ).scalars().all()
    assert len(task_audit) == 1
    assert len(esc_audit) == 1

    # AC-11: no outbound client message and no suggested reply were created.
    outbound = (
        await db_session.execute(
            select(Message).where(
                Message.conversation_id == UUID(conversation["id"]),
                Message.direction == MessageDirection.outbound,
            )
        )
    ).scalars().all()
    replies = (
        await db_session.execute(
            select(SuggestedReply).where(
                SuggestedReply.conversation_id == UUID(conversation["id"])
            )
        )
    ).scalars().all()
    assert outbound == []
    assert replies == []


async def test_apply_true_non_trigger_creates_nothing(
    client: AsyncClient,
    db_session: AsyncSession,
    demo_tenants: dict[str, Tenant],
) -> None:
    token = await login(client)
    conversation = await create_conversation(client, token)
    message = await seed_inbound_message(
        db_session,
        tenant=demo_tenants["elegant-weddings"],
        conversation_id=conversation["id"],
        body="Can you send me the gold package pricing?",
        intent_label="pricing_request",
        risk_level="low",
    )

    response = await run_agent(client, token, conversation["id"], str(message.id), apply=True)

    assert response.status_code == 200
    body = response.json()
    assert body["ran"] is False
    assert body["skipped_reason"] == "intent_not_in_trigger_set"

    tasks = await _tasks_for(db_session, conversation["id"])
    escalations = await _escalations_for(db_session, conversation["id"])
    assert tasks == []
    assert escalations == []


async def test_apply_false_still_creates_nothing(
    client: AsyncClient,
    db_session: AsyncSession,
    demo_tenants: dict[str, Tenant],
) -> None:
    token = await login(client)
    conversation = await create_conversation(client, token)
    message = await seed_inbound_message(
        db_session,
        tenant=demo_tenants["elegant-weddings"],
        conversation_id=conversation["id"],
        intent_label="urgent_change",
        risk_level="high",
    )

    response = await run_agent(client, token, conversation["id"], str(message.id), apply=False)

    assert response.status_code == 200
    assert response.json()["applied"] is None
    assert await _tasks_for(db_session, conversation["id"]) == []
    assert await _escalations_for(db_session, conversation["id"]) == []


async def test_tenant_id_in_body_is_rejected(
    client: AsyncClient,
    db_session: AsyncSession,
    demo_tenants: dict[str, Tenant],
) -> None:
    token = await login(client)
    conversation = await create_conversation(client, token)
    message = await seed_inbound_message(
        db_session,
        tenant=demo_tenants["elegant-weddings"],
        conversation_id=conversation["id"],
    )

    response = await client.post(
        f"/api/v1/conversations/{conversation['id']}/agent/run",
        headers=auth_headers(token),
        json={
            "message_id": str(message.id),
            "apply": False,
            "tenant_id": str(uuid4()),
        },
    )

    assert response.status_code == 422


# --- apply=true idempotency -------------------------------------------------


async def test_apply_true_is_idempotent_for_task_and_escalation(
    client: AsyncClient,
    db_session: AsyncSession,
    demo_tenants: dict[str, Tenant],
) -> None:
    tenant = demo_tenants["elegant-weddings"]
    token = await login(client)
    conversation = await create_conversation(client, token)
    message = await seed_inbound_message(
        db_session,
        tenant=tenant,
        conversation_id=conversation["id"],
        body="We must move the ceremony to tomorrow morning, urgent.",
        intent_label="urgent_change",
        risk_level="medium",
    )

    first = await run_agent(client, token, conversation["id"], str(message.id), apply=True)
    second = await run_agent(client, token, conversation["id"], str(message.id), apply=True)

    assert first.status_code == 200
    assert second.status_code == 200
    first_applied = first.json()["applied"]
    second_applied = second.json()["applied"]

    # Same ids returned on the repeat call...
    assert second_applied["task_id"] == first_applied["task_id"]
    assert second_applied["escalation_id"] == first_applied["escalation_id"]
    assert first_applied["task_id"] is not None
    assert first_applied["escalation_id"] is not None

    # ...and no duplicate rows were created.
    tasks = await _tasks_for(db_session, conversation["id"])
    escalations = await _escalations_for(db_session, conversation["id"])
    assert len(tasks) == 1
    assert len(escalations) == 1
    # Provenance is stamped on the agent records.
    assert tasks[0].source_type == "agent"
    assert tasks[0].source_message_id == message.id
    assert escalations[0].source_type == "agent"
    assert escalations[0].source_message_id == message.id


async def test_apply_true_idempotent_task_only(
    client: AsyncClient,
    db_session: AsyncSession,
    demo_tenants: dict[str, Tenant],
) -> None:
    token = await login(client)
    conversation = await create_conversation(client, token)
    message = await seed_inbound_message(
        db_session,
        tenant=demo_tenants["elegant-weddings"],
        conversation_id=conversation["id"],
        body="I was charged twice and my payment is unconfirmed.",
        intent_label="payment_issue",
        risk_level="medium",
    )

    first = await run_agent(client, token, conversation["id"], str(message.id), apply=True)
    second = await run_agent(client, token, conversation["id"], str(message.id), apply=True)

    assert second.json()["applied"]["task_id"] == first.json()["applied"]["task_id"]
    tasks = await _tasks_for(db_session, conversation["id"])
    escalations = await _escalations_for(db_session, conversation["id"])
    assert len(tasks) == 1
    assert len(escalations) == 0


async def test_apply_true_idempotent_escalation_only(
    client: AsyncClient,
    db_session: AsyncSession,
    demo_tenants: dict[str, Tenant],
) -> None:
    token = await login(client)
    conversation = await create_conversation(client, token)
    message = await seed_inbound_message(
        db_session,
        tenant=demo_tenants["elegant-weddings"],
        conversation_id=conversation["id"],
        body="This is unacceptable and I am very upset.",
        intent_label="complaint",
        risk_level="medium",
    )

    first = await run_agent(client, token, conversation["id"], str(message.id), apply=True)
    second = await run_agent(client, token, conversation["id"], str(message.id), apply=True)

    assert second.json()["applied"]["escalation_id"] == first.json()["applied"]["escalation_id"]
    tasks = await _tasks_for(db_session, conversation["id"])
    escalations = await _escalations_for(db_session, conversation["id"])
    assert len(tasks) == 0
    assert len(escalations) == 1


async def test_agent_task_is_distinct_from_human_task(
    client: AsyncClient,
    db_session: AsyncSession,
    demo_tenants: dict[str, Tenant],
) -> None:
    token = await login(client)
    conversation = await create_conversation(client, token)
    message = await seed_inbound_message(
        db_session,
        tenant=demo_tenants["elegant-weddings"],
        conversation_id=conversation["id"],
        body="I was charged twice and my payment is unconfirmed.",
        intent_label="payment_issue",
        risk_level="medium",
    )

    # A human-created task on the same message (source_type NULL).
    human = await client.post(
        "/api/v1/tasks",
        headers=auth_headers(token),
        json={
            "conversation_id": conversation["id"],
            "message_id": str(message.id),
            "title": "Human follow-up",
        },
    )
    assert human.status_code == 201

    # The agent still creates its own task, then dedups on repeat.
    await run_agent(client, token, conversation["id"], str(message.id), apply=True)
    await run_agent(client, token, conversation["id"], str(message.id), apply=True)

    tasks = await _tasks_for(db_session, conversation["id"])
    assert len(tasks) == 2  # one human (NULL source) + one agent
    agent_tasks = [t for t in tasks if t.source_type == "agent"]
    human_tasks = [t for t in tasks if t.source_type is None]
    assert len(agent_tasks) == 1
    assert len(human_tasks) == 1
