import pytest
from httpx import AsyncClient


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


async def test_elegant_can_simulate_new_whatsapp_message(client: AsyncClient):
    token = await login(client, "admin@elegant-weddings.demo", "demo-password-1")

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
    assert data["conversation"]["client_name"] == "Maya Haddad"
    assert data["conversation"]["client_contact"] == "+96170111222"
    assert data["message"]["conversation_id"] == data["conversation"]["id"]
    assert data["message"]["direction"] == "inbound"
    assert data["message"]["source"] == "whatsapp_simulator"
    assert data["message"]["body"] == "Hi, can you send me your wedding package prices?"


async def test_simulator_creates_new_conversation_when_missing_conversation_id(
    client: AsyncClient,
):
    token = await login(client, "admin@elegant-weddings.demo", "demo-password-1")

    response = await client.post(
        "/api/v1/simulator/messages",
        headers=auth_headers(token),
        json={"client_name": "Maya Haddad", "body": "Hello from WhatsApp"},
    )
    assert response.status_code == 201
    conversation_id = response.json()["conversation"]["id"]

    list_response = await client.get("/api/v1/conversations", headers=auth_headers(token))
    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()] == [conversation_id]


async def test_simulator_adds_inbound_message_to_existing_conversation(client: AsyncClient):
    token = await login(client, "admin@elegant-weddings.demo", "demo-password-1")

    create_response = await client.post(
        "/api/v1/conversations",
        headers=auth_headers(token),
        json={"client_name": "Maya Haddad", "client_contact": "+96170111222"},
    )
    assert create_response.status_code == 201
    conversation_id = create_response.json()["id"]

    simulate_response = await client.post(
        "/api/v1/simulator/messages",
        headers=auth_headers(token),
        json={
            "conversation_id": conversation_id,
            "body": "Also, do you have availability on August 15?",
        },
    )
    assert simulate_response.status_code == 201
    assert simulate_response.json()["message"]["direction"] == "inbound"

    messages_response = await client.get(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=auth_headers(token),
    )
    assert messages_response.status_code == 200
    messages = messages_response.json()
    assert len(messages) == 1
    assert messages[0]["body"] == "Also, do you have availability on August 15?"
    assert messages[0]["direction"] == "inbound"


async def test_royal_cannot_add_message_to_elegant_conversation(client: AsyncClient):
    elegant_token = await login(client, "admin@elegant-weddings.demo", "demo-password-1")
    royal_token = await login(client, "admin@royal-events.demo", "demo-password-2")

    create_response = await client.post(
        "/api/v1/simulator/messages",
        headers=auth_headers(elegant_token),
        json={"client_name": "Maya Haddad", "body": "Elegant-only message"},
    )
    assert create_response.status_code == 201
    conversation_id = create_response.json()["conversation"]["id"]

    response = await client.post(
        "/api/v1/simulator/messages",
        headers=auth_headers(royal_token),
        json={"conversation_id": conversation_id, "body": "Cross-tenant injection attempt"},
    )
    assert response.status_code == 403
    assert response.json() == {"detail": "forbidden"}


async def test_royal_cannot_see_elegant_simulated_messages(client: AsyncClient):
    elegant_token = await login(client, "admin@elegant-weddings.demo", "demo-password-1")
    royal_token = await login(client, "admin@royal-events.demo", "demo-password-2")

    create_response = await client.post(
        "/api/v1/simulator/messages",
        headers=auth_headers(elegant_token),
        json={"client_name": "Maya Haddad", "body": "Elegant-only message"},
    )
    assert create_response.status_code == 201
    conversation_id = create_response.json()["conversation"]["id"]

    royal_list_response = await client.get(
        "/api/v1/conversations",
        headers=auth_headers(royal_token),
    )
    assert royal_list_response.status_code == 200
    assert royal_list_response.json() == []

    royal_messages_response = await client.get(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=auth_headers(royal_token),
    )
    assert royal_messages_response.status_code == 403


async def test_simulator_ignores_client_supplied_tenant_id(client: AsyncClient):
    elegant_token = await login(client, "admin@elegant-weddings.demo", "demo-password-1")
    royal_token = await login(client, "admin@royal-events.demo", "demo-password-2")

    royal_tenant_response = await client.get(
        "/api/v1/tenants/me",
        headers=auth_headers(royal_token),
    )
    assert royal_tenant_response.status_code == 200
    royal_tenant_id = royal_tenant_response.json()["id"]

    response = await client.post(
        "/api/v1/simulator/messages",
        headers=auth_headers(elegant_token),
        json={
            "tenant_id": royal_tenant_id,
            "client_name": "Maya Haddad",
            "body": "This must stay in Elegant's tenant",
        },
    )
    assert response.status_code == 201
    data = response.json()

    elegant_tenant_response = await client.get(
        "/api/v1/tenants/me",
        headers=auth_headers(elegant_token),
    )
    assert elegant_tenant_response.status_code == 200
    elegant_tenant_id = elegant_tenant_response.json()["id"]

    assert data["conversation"]["tenant_id"] == elegant_tenant_id
    assert data["message"]["tenant_id"] == elegant_tenant_id
    assert data["conversation"]["tenant_id"] != royal_tenant_id
