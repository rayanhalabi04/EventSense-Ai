from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.escalation import Escalation
from app.models.audit_log import AuditLog
from app.models.message import Message, MessageDirection
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


async def test_apply_true_is_rejected_and_creates_nothing(
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

    response = await run_agent(client, token, conversation["id"], str(message.id), apply=True)

    assert response.status_code == 422
    assert response.json()["error_code"] == "agent_apply_not_enabled"

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
