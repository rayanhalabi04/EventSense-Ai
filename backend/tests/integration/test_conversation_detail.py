from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.services.audit_log_service import AUDIT_EVENT_CONVERSATION_DETAIL_VIEWED


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


async def create_simulator_message(client: AsyncClient, token: str, body: str) -> dict[str, object]:
    response = await client.post(
        "/api/v1/simulator/messages",
        headers=auth_headers(token),
        json={"client_name": "Detail Client", "client_contact": "+96170111222", "body": body},
    )
    assert response.status_code == 201
    return response.json()


async def get_detail(client: AsyncClient, token: str, conversation_id: str):
    return await client.get(
        f"/api/v1/conversations/{conversation_id}/detail",
        headers=auth_headers(token),
    )


async def test_tenant_user_can_view_own_conversation_detail(client: AsyncClient):
    token = await login(client)
    simulated = await create_simulator_message(
        client,
        token,
        "Hi, can you send me your wedding package prices?",
    )

    response = await get_detail(client, token, simulated["conversation_id"])

    assert response.status_code == 200
    data = response.json()
    assert data["conversation_id"] == simulated["conversation_id"]
    assert data["client_name"] == "Detail Client"
    assert data["client_contact"] == "+96170111222"
    assert data["conversation_status"] == "open"
    assert data["created_at"] is not None
    assert data["updated_at"] is not None
    assert data["latest_inbound_message"]["id"] == simulated["message_id"]


async def test_tenant_user_cannot_view_other_tenant_conversation_detail(
    client: AsyncClient,
):
    elegant_token = await login(client)
    royal_token = await login(
        client,
        email="admin@royal-events.demo",
        password="demo-password-2",
        tenant_slug="royal-events-agency",
    )
    simulated = await create_simulator_message(client, elegant_token, "Elegant-only detail")

    response = await get_detail(client, royal_token, simulated["conversation_id"])

    assert response.status_code == 403


async def test_detail_response_includes_messages_in_chronological_order(
    client: AsyncClient,
):
    token = await login(client)
    simulated = await create_simulator_message(client, token, "First inbound message")
    outbound = await client.post(
        f"/api/v1/conversations/{simulated['conversation_id']}/messages",
        headers=auth_headers(token),
        json={"direction": "outbound", "body": "Second outbound message"},
    )
    assert outbound.status_code == 201

    response = await get_detail(client, token, simulated["conversation_id"])

    assert response.status_code == 200
    messages = response.json()["messages"]
    assert [message["body"] for message in messages] == [
        "First inbound message",
        "Second outbound message",
    ]


async def test_detail_response_includes_intent_and_risk_fields(client: AsyncClient):
    token = await login(client)
    simulated = await create_simulator_message(
        client,
        token,
        "I am unhappy and want to cancel this event.",
    )

    response = await get_detail(client, token, simulated["conversation_id"])

    assert response.status_code == 200
    data = response.json()
    assert data["latest_intent_label"] is not None
    assert data["latest_intent_confidence"] is not None
    assert data["latest_classified_at"] is not None
    assert data["latest_risk_level"] == "high"
    assert data["latest_risk_flags"] == ["complaint"]
    assert data["latest_risk_reason"] is not None
    assert data["latest_risk_detected_at"] is not None
    latest = data["latest_inbound_message"]
    assert latest["intent_label"] == data["latest_intent_label"]
    assert latest["risk_level"] == data["latest_risk_level"]


async def test_detail_response_includes_future_placeholders(client: AsyncClient):
    token = await login(client)
    simulated = await create_simulator_message(client, token, "Can you send pricing?")

    response = await get_detail(client, token, simulated["conversation_id"])

    assert response.status_code == 200
    data = response.json()
    assert data["suggested_reply"] is None
    assert data["rag_sources"] == []
    assert data["tasks"] == []
    assert data["escalations"] == []


async def test_detail_view_creates_audit_log_event(
    client: AsyncClient,
    db_session: AsyncSession,
):
    token = await login(client)
    simulated = await create_simulator_message(client, token, "Can you send pricing?")

    response = await get_detail(client, token, simulated["conversation_id"])

    assert response.status_code == 200
    result = await db_session.execute(
        select(AuditLog).where(AuditLog.event_type == AUDIT_EVENT_CONVERSATION_DETAIL_VIEWED)
    )
    logs = list(result.scalars().all())
    assert len(logs) == 1
    assert logs[0].resource_type == "conversation"
    assert logs[0].resource_id == simulated["conversation_id"]
    assert logs[0].details["conversation_id"] == simulated["conversation_id"]
    assert logs[0].details["user_id"] is not None
    assert any(
        item["event_type"] == AUDIT_EVENT_CONVERSATION_DETAIL_VIEWED
        for item in response.json()["audit_timeline"]
    )


async def test_nonexistent_conversation_detail_returns_404(client: AsyncClient):
    token = await login(client)

    response = await get_detail(client, token, str(uuid4()))

    assert response.status_code == 404
    assert response.json()["detail"] == "conversation not found"
