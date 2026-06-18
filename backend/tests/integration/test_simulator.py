from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.conversation import Conversation, ConversationStatus
from app.models.message import Message, MessageDirection, MessageStatus
from app.models.task import Task, TaskStatus
from app.models.user import User, UserRole
from app.services.intent_classifier_service import INTENT_LABELS, IntentClassification


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


async def elegant_token(client: AsyncClient) -> str:
    return await login(client, "admin@elegant-weddings.demo", "demo-password-1")


async def royal_token(client: AsyncClient) -> str:
    return await login(client, "admin@royal-events.demo", "demo-password-2")


async def platform_token(client: AsyncClient) -> str:
    return await login(client, "platform-admin@eventsense.demo", "platform-password")


async def test_simulator_creates_inbound_message_with_correct_fields(
    client: AsyncClient,
    db_session: AsyncSession,
):
    token = await elegant_token(client)

    response = await client.post(
        "/api/v1/simulator/messages",
        headers=auth_headers(token),
        json={
            "client_name": "Maya Haddad",
            "client_contact": "+96170111222",
            "body": "Hi, can you send me your wedding package prices?",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["is_new_conversation"] is True
    assert data["conversation_status"] == "open"
    assert data["intent_label"] in INTENT_LABELS
    assert data["intent_label"] == "pricing_request"
    assert 0.0 <= data["intent_confidence"] <= 1.0
    assert data["classified_at"] is not None

    message = await db_session.get(Message, UUID(data["message_id"]))
    conversation = await db_session.get(Conversation, UUID(data["conversation_id"]))
    assert message is not None
    assert conversation is not None
    assert message.tenant_id == conversation.tenant_id
    assert str(message.tenant_id) == data["tenant_id"]
    assert message.conversation_id == conversation.id
    assert message.direction is MessageDirection.inbound
    assert message.status is MessageStatus.unread
    assert message.source == "whatsapp_simulator"
    assert message.body == "Hi, can you send me your wedding package prices?"
    assert message.intent_label == data["intent_label"]
    assert message.intent_confidence == data["intent_confidence"]
    assert message.classified_at is not None


@pytest.mark.parametrize(
    "body",
    [
        "I want to ask about your wedding packages.",
        "Can you send me your wedding package prices?",
        "What packages do you offer for weddings?",
    ],
)
async def test_simulator_package_pricing_messages_route_to_pricing_request(
    client: AsyncClient,
    body: str,
):
    token = await elegant_token(client)

    response = await client.post(
        "/api/v1/simulator/messages",
        headers=auth_headers(token),
        json={"client_name": "Maya Haddad", "body": body},
    )

    assert response.status_code == 201
    assert response.json()["intent_label"] == "pricing_request"


async def test_simulator_stores_inbound_message_memory(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    token = await elegant_token(client)
    recorded = []

    class FakeMemoryService:
        async def store_inbound_message(self, *, tenant_id, message):
            recorded.append((tenant_id, message))

    monkeypatch.setattr(
        "app.api.v1.simulator.ConversationMemoryService",
        lambda: FakeMemoryService(),
    )

    response = await client.post(
        "/api/v1/simulator/messages",
        headers=auth_headers(token),
        json={"client_name": "Maya Haddad", "body": "Please remember this."},
    )

    assert response.status_code == 201
    assert len(recorded) == 1
    tenant_id, message = recorded[0]
    assert str(tenant_id) == response.json()["tenant_id"]
    assert str(message.id) == response.json()["message_id"]


async def test_simulator_task_worthy_message_creates_follow_up_task(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    token = await elegant_token(client)
    monkeypatch.setattr(
        "app.services.simulator_service.IntentClassifierService.classify",
        lambda body: IntentClassification(label="guest_count_change", confidence=0.95),
    )

    response = await client.post(
        "/api/v1/simulator/messages",
        headers=auth_headers(token),
        json={
            "client_name": "Maya Haddad",
            "body": "We need to change our guest count from 80 to 150 for next week.",
        },
    )

    assert response.status_code == 201
    conversation_id = UUID(response.json()["conversation_id"])
    message_id = UUID(response.json()["message_id"])
    tasks = (
        await db_session.execute(
            select(Task).where(Task.conversation_id == conversation_id)
        )
    ).scalars().all()
    assert len(tasks) == 1
    assert tasks[0].message_id == message_id
    assert tasks[0].title == "Review guest count change"
    assert tasks[0].status is TaskStatus.open
    assert tasks[0].source_type == "inbound_auto"


async def test_simulator_creates_new_conversation_for_unknown_client(client: AsyncClient):
    token = await elegant_token(client)

    response = await client.post(
        "/api/v1/simulator/messages",
        headers=auth_headers(token),
        json={"client_name": "Maya Haddad", "body": "Hello from WhatsApp"},
    )

    assert response.status_code == 201
    assert response.json()["is_new_conversation"] is True


async def test_simulator_reuses_matching_conversation_case_insensitively(
    client: AsyncClient,
):
    token = await elegant_token(client)
    first = await client.post(
        "/api/v1/simulator/messages",
        headers=auth_headers(token),
        json={"client_name": "Maya Haddad", "client_contact": "+9617", "body": "First"},
    )
    second = await client.post(
        "/api/v1/simulator/messages",
        headers=auth_headers(token),
        json={"client_name": "maya haddad", "client_contact": "+9617", "body": "Second"},
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["is_new_conversation"] is False
    assert second.json()["conversation_id"] == first.json()["conversation_id"]


async def test_simulator_appends_to_existing_conversation(
    client: AsyncClient,
    db_session: AsyncSession,
):
    token = await elegant_token(client)
    first = await client.post(
        "/api/v1/simulator/messages",
        headers=auth_headers(token),
        json={"client_name": "Maya Haddad", "body": "First"},
    )
    conversation_id = first.json()["conversation_id"]

    second = await client.post(
        "/api/v1/simulator/messages",
        headers=auth_headers(token),
        json={"conversation_id": conversation_id, "body": "Follow-up"},
    )

    assert second.status_code == 201
    assert second.json()["is_new_conversation"] is False
    assert second.json()["conversation_id"] == conversation_id
    messages = (
        await db_session.execute(
            select(Message).where(Message.conversation_id == UUID(conversation_id))
        )
    ).scalars().all()
    assert [message.body for message in messages] == ["First", "Follow-up"]


async def test_simulator_reopens_closed_conversation(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    token = await elegant_token(client)
    created = await client.post(
        "/api/v1/simulator/messages",
        headers=auth_headers(token),
        json={"client_name": "Maya Haddad", "body": "First"},
    )
    conversation = await db_session.get(Conversation, UUID(created.json()["conversation_id"]))
    assert conversation is not None
    conversation.status = ConversationStatus.closed
    await db_session.commit()

    events = []

    def record_event(action: str, **details: object) -> None:
        events.append({"action": action, **details})

    monkeypatch.setattr("app.api.v1.simulator.emit_simulator_event", record_event)
    response = await client.post(
        "/api/v1/simulator/messages",
        headers=auth_headers(token),
        json={"conversation_id": str(conversation.id), "body": "Please reopen"},
    )

    assert response.status_code == 201
    assert response.json()["conversation_status"] == "open"
    await db_session.refresh(conversation)
    assert conversation.status is ConversationStatus.open
    assert len(events) == 1
    assert events[0]["reopened"] is True


async def test_simulator_rejects_empty_body(client: AsyncClient):
    response = await client.post(
        "/api/v1/simulator/messages",
        headers=auth_headers(await elegant_token(client)),
        json={"client_name": "Maya Haddad", "body": ""},
    )

    assert response.status_code == 422


async def test_simulator_rejects_whitespace_only_body(client: AsyncClient):
    response = await client.post(
        "/api/v1/simulator/messages",
        headers=auth_headers(await elegant_token(client)),
        json={"client_name": "Maya Haddad", "body": "   "},
    )

    assert response.status_code == 422


async def test_simulator_rejects_body_exceeding_4000_chars(client: AsyncClient):
    response = await client.post(
        "/api/v1/simulator/messages",
        headers=auth_headers(await elegant_token(client)),
        json={"client_name": "Maya Haddad", "body": "x" * 4001},
    )

    assert response.status_code == 422


async def test_simulator_requires_conversation_id_or_client_name(client: AsyncClient):
    response = await client.post(
        "/api/v1/simulator/messages",
        headers=auth_headers(await elegant_token(client)),
        json={"body": "No target"},
    )

    assert response.status_code == 422


async def test_simulator_emits_event_on_success_if_available(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    events = []

    def record_event(action: str, **details: object) -> None:
        events.append({"action": action, **details})

    monkeypatch.setattr("app.api.v1.simulator.emit_simulator_event", record_event)

    response = await client.post(
        "/api/v1/simulator/messages",
        headers=auth_headers(await elegant_token(client)),
        json={"client_name": "Maya Haddad", "body": "Event please"},
    )

    assert response.status_code == 201
    assert len(events) == 1
    assert events[0]["action"] == "simulator_message_created"
    assert str(events[0]["conversation_id"]) == response.json()["conversation_id"]
    assert str(events[0]["resource_id"]) == response.json()["message_id"]
    assert events[0]["client_name"] == "Maya Haddad"
    assert events[0]["is_new_conversation"] is True


async def test_simulator_message_invisible_to_other_tenant(client: AsyncClient):
    elegant = await elegant_token(client)
    royal = await royal_token(client)

    await client.post(
        "/api/v1/simulator/messages",
        headers=auth_headers(elegant),
        json={"client_name": "Maya Haddad", "body": "Elegant-only message"},
    )

    royal_list_response = await client.get(
        "/api/v1/conversations",
        headers=auth_headers(royal),
    )
    assert royal_list_response.status_code == 200
    assert royal_list_response.json() == []


async def test_simulator_conversation_list_scoped_to_tenant(client: AsyncClient):
    elegant = await elegant_token(client)
    royal = await royal_token(client)
    await client.post(
        "/api/v1/simulator/messages",
        headers=auth_headers(elegant),
        json={"client_name": "Elegant Client", "body": "Elegant-only message"},
    )
    await client.post(
        "/api/v1/simulator/messages",
        headers=auth_headers(royal),
        json={"client_name": "Royal Client", "body": "Royal-only message"},
    )

    response = await client.get("/api/v1/simulator/conversations", headers=auth_headers(elegant))

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["client_name"] == "Elegant Client"
    assert data["items"][0]["message_count"] == 1


async def test_simulator_cross_tenant_conversation_id_returns_403(client: AsyncClient):
    elegant = await elegant_token(client)
    royal = await royal_token(client)
    create_response = await client.post(
        "/api/v1/simulator/messages",
        headers=auth_headers(elegant),
        json={"client_name": "Maya Haddad", "body": "Elegant-only message"},
    )

    response = await client.post(
        "/api/v1/simulator/messages",
        headers=auth_headers(royal),
        json={
            "conversation_id": create_response.json()["conversation_id"],
            "body": "Cross-tenant injection attempt",
        },
    )

    assert response.status_code == 403
    assert response.json()["error_code"] == "CROSS_TENANT_ACCESS"


async def test_simulator_platform_admin_returns_403(client: AsyncClient):
    response = await client.post(
        "/api/v1/simulator/messages",
        headers=auth_headers(await platform_token(client)),
        json={"client_name": "Maya Haddad", "body": "Platform attempt"},
    )

    assert response.status_code == 403
    assert response.json()["error_code"] == "INSUFFICIENT_ROLE"


async def test_simulator_requires_authentication(client: AsyncClient):
    response = await client.post(
        "/api/v1/simulator/messages",
        json={"client_name": "Maya Haddad", "body": "No auth"},
    )

    assert response.status_code == 401
    assert response.json()["error_code"] == "MISSING_TOKEN"


async def test_simulator_rejects_invalid_token(client: AsyncClient):
    response = await client.post(
        "/api/v1/simulator/messages",
        headers=auth_headers("not-a-token"),
        json={"client_name": "Maya Haddad", "body": "Bad auth"},
    )

    assert response.status_code == 401
    assert response.json()["error_code"] == "INVALID_TOKEN"


async def test_simulator_tenant_id_from_jwt_not_body(client: AsyncClient):
    elegant = await elegant_token(client)
    royal = await royal_token(client)
    royal_tenant_response = await client.get("/api/v1/tenants/me", headers=auth_headers(royal))
    royal_tenant_id = royal_tenant_response.json()["id"]

    response = await client.post(
        "/api/v1/simulator/messages",
        headers=auth_headers(elegant),
        json={
            "tenant_id": royal_tenant_id,
            "client_name": "Maya Haddad",
            "body": "This must stay in Elegant's tenant",
        },
    )

    assert response.status_code == 201
    assert response.json()["tenant_id"] != royal_tenant_id
    assert response.json()["intent_label"] in INTENT_LABELS


async def test_staff_can_create_simulator_message(
    client: AsyncClient,
    db_session: AsyncSession,
):
    tenant_response = await client.get(
        "/api/v1/tenants/me",
        headers=auth_headers(await elegant_token(client)),
    )
    user = User(
        tenant_id=UUID(tenant_response.json()["id"]),
        email="staff@elegant-weddings.demo",
        hashed_password=hash_password("staff-password-1"),
        role=UserRole.staff,
        full_name="Elegant Staff",
    )
    db_session.add(user)
    await db_session.commit()
    token = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "staff@elegant-weddings.demo",
            "password": "staff-password-1",
            "tenant_slug": "elegant-weddings",
        },
    )
    assert token.status_code == 200

    response = await client.post(
        "/api/v1/simulator/messages",
        headers=auth_headers(token.json()["access_token"]),
        json={"client_name": "Staff Client", "body": "Created by staff"},
    )

    assert response.status_code == 201
