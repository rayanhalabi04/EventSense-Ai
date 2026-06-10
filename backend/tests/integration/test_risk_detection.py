import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.services.audit_log_service import AUDIT_EVENT_MESSAGE_RISK_DETECTED


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


async def simulate_message(
    client: AsyncClient,
    token: str,
    body: str,
    client_name: str = "Risk Client",
) -> dict[str, object]:
    response = await client.post(
        "/api/v1/simulator/messages",
        headers=auth_headers(token),
        json={"client_name": client_name, "body": body},
    )
    assert response.status_code == 201
    return response.json()


async def test_simulator_persists_pricing_low_risk_and_inbox_returns_real_risk(
    client: AsyncClient,
):
    token = await login(client)

    simulated = await simulate_message(
        client,
        token,
        "Hi, can you send me your wedding package prices?",
    )
    inbox_response = await client.get("/api/v1/inbox", headers=auth_headers(token))

    assert simulated["risk_level"] == "low"
    assert simulated["risk_flags"] == []
    assert simulated["risk_reason"] == "pricing_request is a routine planning request."
    assert simulated["risk_detected_at"] is not None
    assert inbox_response.status_code == 200
    item = inbox_response.json()["items"][0]
    assert item["latest_message_id"] == simulated["message_id"]
    assert item["risk_level"] == "low"
    assert item["risk_flags"] == []
    assert item["risk_reason"] == simulated["risk_reason"]
    assert item["risk_detected_at"] is not None


async def test_risk_detection_is_tenant_scoped_through_simulator_and_inbox(
    client: AsyncClient,
):
    elegant_token = await login(client)
    royal_token = await login(
        client,
        email="admin@royal-events.demo",
        password="demo-password-2",
        tenant_slug="royal-events-agency",
    )
    elegant_message = await simulate_message(
        client,
        elegant_token,
        "I want to cancel our booking immediately.",
        client_name="Elegant Risk Client",
    )
    await simulate_message(
        client,
        royal_token,
        "Can you send your pricing?",
        client_name="Royal Risk Client",
    )

    royal_inbox = await client.get("/api/v1/inbox", headers=auth_headers(royal_token))

    assert royal_inbox.status_code == 200
    assert all(
        item["latest_message_id"] != elegant_message["message_id"]
        for item in royal_inbox.json()["items"]
    )
    assert {item["risk_level"] for item in royal_inbox.json()["items"]} == {"low"}


async def test_audit_log_created_for_risk_detection(
    client: AsyncClient,
    db_session: AsyncSession,
):
    token = await login(client)

    simulated = await simulate_message(
        client,
        token,
        "I am unhappy and want to cancel this event.",
    )

    result = await db_session.execute(
        select(AuditLog).where(AuditLog.event_type == AUDIT_EVENT_MESSAGE_RISK_DETECTED)
    )
    logs = list(result.scalars().all())
    assert len(logs) == 1
    assert logs[0].resource_type == "message"
    assert logs[0].resource_id == simulated["message_id"]
    assert logs[0].details["risk_level"] == "high"
    assert logs[0].details["risk_flags"] == ["complaint"]
