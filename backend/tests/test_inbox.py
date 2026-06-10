from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.models.message import Message, MessageDirection
from app.models.tenant import Tenant
from app.services.intent_classifier_service import INTENT_LABELS


pytestmark = pytest.mark.asyncio


async def login(client: AsyncClient, email: str, password: str) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def get_tenant(db_session: AsyncSession, slug: str) -> Tenant:
    result = await db_session.execute(select(Tenant).where(Tenant.slug == slug))
    tenant = result.scalar_one()
    return tenant


async def create_message_for_tenant(
    db_session: AsyncSession,
    tenant: Tenant,
    client_name: str,
    body: str,
    sent_at: datetime,
    conversation: Conversation | None = None,
) -> tuple[Conversation, Message]:
    if conversation is None:
        conversation = Conversation(
            tenant_id=tenant.id,
            client_name=client_name,
            client_contact=f"{client_name.lower().replace(' ', '.')}@example.com",
        )
        db_session.add(conversation)
        await db_session.flush()

    message = Message(
        tenant_id=tenant.id,
        conversation_id=conversation.id,
        direction=MessageDirection.inbound,
        body=body,
        source="whatsapp_simulator",
        sent_at=sent_at,
    )
    db_session.add(message)
    await db_session.commit()
    return conversation, message


async def test_elegant_sees_own_simulated_message_in_inbox(client: AsyncClient):
    token = await login(client, "admin@elegant-weddings.demo", "demo-password-1")

    simulate_response = await client.post(
        "/api/v1/simulator/messages",
        headers=auth_headers(token),
        json={
            "client_name": "Maya Haddad",
            "client_contact": "+96170111222",
            "body": "Hi, can you send me your wedding package prices?",
        },
    )
    assert simulate_response.status_code == 201
    simulated = simulate_response.json()

    inbox_response = await client.get("/api/v1/inbox/messages", headers=auth_headers(token))
    assert inbox_response.status_code == 200
    rows = inbox_response.json()

    assert len(rows) == 1
    assert rows[0]["conversation_id"] == simulated["conversation_id"]
    assert rows[0]["latest_message_id"] == simulated["message_id"]
    assert rows[0]["client_name"] == "Maya Haddad"
    assert rows[0]["client_contact"] == "+96170111222"
    assert rows[0]["message_preview"] == "Hi, can you send me your wedding package prices?"
    assert rows[0]["latest_message_body"] == "Hi, can you send me your wedding package prices?"
    assert rows[0]["status"] == "open"
    assert rows[0]["source"] == "whatsapp_simulator"
    assert rows[0]["direction"] == "inbound"
    assert rows[0]["intent_label"] in INTENT_LABELS
    assert rows[0]["intent_label"] == "pricing_request"
    assert 0.0 <= rows[0]["intent_confidence"] <= 1.0
    assert rows[0]["classified_at"] is not None
    assert rows[0]["risk_level"] == "low"
    assert rows[0]["risk_flags"] == []
    assert rows[0]["risk_reason"] == "pricing_request is a routine planning request."
    assert rows[0]["risk_detected_at"] is not None


async def test_royal_does_not_see_elegant_inbox_message(client: AsyncClient):
    elegant_token = await login(client, "admin@elegant-weddings.demo", "demo-password-1")
    royal_token = await login(client, "admin@royal-events.demo", "demo-password-2")

    simulate_response = await client.post(
        "/api/v1/simulator/messages",
        headers=auth_headers(elegant_token),
        json={"client_name": "Maya Haddad", "body": "Elegant-only message"},
    )
    assert simulate_response.status_code == 201

    royal_response = await client.get("/api/v1/inbox/messages", headers=auth_headers(royal_token))
    assert royal_response.status_code == 200
    assert royal_response.json() == []


async def test_inbox_returns_latest_message_per_conversation(
    client: AsyncClient,
    db_session: AsyncSession,
):
    token = await login(client, "admin@elegant-weddings.demo", "demo-password-1")
    elegant = await get_tenant(db_session, "elegant-weddings")
    base_time = datetime(2026, 6, 6, 10, 0, tzinfo=timezone.utc)

    conversation, first_message = await create_message_for_tenant(
        db_session, elegant, "Maya Haddad", "First question", base_time
    )
    _, second_message = await create_message_for_tenant(
        db_session,
        elegant,
        "Maya Haddad",
        "Latest question about availability",
        base_time + timedelta(minutes=5),
        conversation=conversation,
    )

    response = await client.get("/api/v1/inbox/messages", headers=auth_headers(token))
    assert response.status_code == 200
    rows = response.json()

    assert len(rows) == 1
    assert rows[0]["conversation_id"] == str(conversation.id)
    assert rows[0]["latest_message_id"] == str(second_message.id)
    assert rows[0]["latest_message_id"] != str(first_message.id)
    assert rows[0]["latest_message_body"] == "Latest question about availability"


async def test_inbox_is_sorted_newest_first(client: AsyncClient, db_session: AsyncSession):
    token = await login(client, "admin@elegant-weddings.demo", "demo-password-1")
    elegant = await get_tenant(db_session, "elegant-weddings")
    base_time = datetime(2026, 6, 6, 10, 0, tzinfo=timezone.utc)

    older_conversation, _ = await create_message_for_tenant(
        db_session, elegant, "Older Client", "Older message", base_time
    )
    newer_conversation, _ = await create_message_for_tenant(
        db_session,
        elegant,
        "Newer Client",
        "Newer message",
        base_time + timedelta(hours=1),
    )

    response = await client.get("/api/v1/inbox/messages", headers=auth_headers(token))
    assert response.status_code == 200
    rows = response.json()

    assert [row["conversation_id"] for row in rows] == [
        str(newer_conversation.id),
        str(older_conversation.id),
    ]


async def test_inbox_ignores_client_supplied_tenant_id(client: AsyncClient):
    elegant_token = await login(client, "admin@elegant-weddings.demo", "demo-password-1")
    royal_token = await login(client, "admin@royal-events.demo", "demo-password-2")

    royal_tenant_response = await client.get(
        "/api/v1/tenants/me",
        headers=auth_headers(royal_token),
    )
    assert royal_tenant_response.status_code == 200
    royal_tenant_id = royal_tenant_response.json()["id"]

    simulate_response = await client.post(
        "/api/v1/simulator/messages",
        headers=auth_headers(elegant_token),
        json={"client_name": "Maya Haddad", "body": "Must remain Elegant-only"},
    )
    assert simulate_response.status_code == 201

    inbox_response = await client.get(
        f"/api/v1/inbox/messages?tenant_id={royal_tenant_id}",
        headers=auth_headers(elegant_token),
    )
    assert inbox_response.status_code == 200
    rows = inbox_response.json()
    assert len(rows) == 1
    assert rows[0]["latest_message_id"] == simulate_response.json()["message_id"]


async def test_inbox_requires_authentication(client: AsyncClient):
    response = await client.get("/api/v1/inbox/messages")
    assert response.status_code == 401
