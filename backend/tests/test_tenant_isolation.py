import pytest
from httpx import AsyncClient


pytestmark = pytest.mark.asyncio


async def login(client: AsyncClient, email: str, password: str) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["token_type"] == "bearer"
    return data["access_token"]


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_login_works_for_both_demo_users(client: AsyncClient):
    elegant_token = await login(client, "admin@elegant-weddings.demo", "demo-password-1")
    royal_token = await login(client, "admin@royal-events.demo", "demo-password-2")

    assert elegant_token
    assert royal_token
    assert elegant_token != royal_token


async def test_tenant_a_can_create_and_list_own_conversation(client: AsyncClient):
    token = await login(client, "admin@elegant-weddings.demo", "demo-password-1")

    create_response = await client.post(
        "/api/v1/conversations",
        headers=auth_headers(token),
        json={"client_name": "Alice Johnson", "client_contact": "alice@example.com"},
    )
    assert create_response.status_code == 201
    created = create_response.json()

    list_response = await client.get("/api/v1/conversations", headers=auth_headers(token))
    assert list_response.status_code == 200
    conversations = list_response.json()
    assert [item["id"] for item in conversations] == [created["id"]]


async def test_tenant_b_cannot_see_tenant_a_conversation(client: AsyncClient):
    elegant_token = await login(client, "admin@elegant-weddings.demo", "demo-password-1")
    royal_token = await login(client, "admin@royal-events.demo", "demo-password-2")

    create_response = await client.post(
        "/api/v1/conversations",
        headers=auth_headers(elegant_token),
        json={"client_name": "Alice Johnson"},
    )
    assert create_response.status_code == 201
    conversation_id = create_response.json()["id"]

    list_response = await client.get("/api/v1/conversations", headers=auth_headers(royal_token))
    assert list_response.status_code == 200
    assert list_response.json() == []

    detail_response = await client.get(
        f"/api/v1/conversations/{conversation_id}",
        headers=auth_headers(royal_token),
    )
    assert detail_response.status_code == 403
    assert detail_response.json() == {"detail": "forbidden"}


async def test_client_supplied_tenant_id_is_ignored(client: AsyncClient):
    elegant_token = await login(client, "admin@elegant-weddings.demo", "demo-password-1")
    royal_token = await login(client, "admin@royal-events.demo", "demo-password-2")

    royal_tenant_response = await client.get("/api/v1/tenants/me", headers=auth_headers(royal_token))
    assert royal_tenant_response.status_code == 200
    royal_tenant_id = royal_tenant_response.json()["id"]

    create_response = await client.post(
        "/api/v1/conversations",
        headers=auth_headers(elegant_token),
        json={
            "tenant_id": royal_tenant_id,
            "client_name": "Ignored Tenant Payload",
            "client_contact": "payload@example.com",
        },
    )
    assert create_response.status_code == 201
    created = create_response.json()

    elegant_tenant_response = await client.get(
        "/api/v1/tenants/me", headers=auth_headers(elegant_token)
    )
    assert elegant_tenant_response.status_code == 200
    assert created["tenant_id"] == elegant_tenant_response.json()["id"]
    assert created["tenant_id"] != royal_tenant_id
