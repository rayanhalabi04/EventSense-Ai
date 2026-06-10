from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.audit_log import AuditLog
from app.models.tenant import Tenant
from app.models.user import User, UserRole
from app.services.audit_log_service import AUDIT_EVENT_ESCALATION_STATUS_CHANGED


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


async def create_staff_user(db_session: AsyncSession, tenant: Tenant) -> User:
    staff = User(
        tenant_id=tenant.id,
        email=f"staff-{uuid4()}@elegant-weddings.demo",
        hashed_password=hash_password("staff-password"),
        role=UserRole.staff,
        full_name="Elegant Staff",
    )
    db_session.add(staff)
    await db_session.commit()
    await db_session.refresh(staff)
    return staff


def token_for(user: User) -> str:
    return create_access_token(sub=user.id, tenant_id=user.tenant_id, role=user.role.value)


async def get_manager_user(db_session: AsyncSession, email: str) -> User:
    result = await db_session.execute(select(User).where(User.email == email))
    manager = result.scalar_one()
    assert manager.role == UserRole.manager
    return manager


async def create_conversation(
    client: AsyncClient,
    token: str,
    client_name: str = "Escalation Client",
) -> dict:
    response = await client.post(
        "/api/v1/conversations",
        headers=auth_headers(token),
        json={"client_name": client_name, "client_contact": "+96170000000"},
    )
    assert response.status_code == 201
    return response.json()


async def create_message(client: AsyncClient, token: str, conversation_id: str, body: str) -> dict:
    response = await client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=auth_headers(token),
        json={"direction": "inbound", "body": body},
    )
    assert response.status_code == 201
    return response.json()


async def create_escalation(
    client: AsyncClient,
    token: str,
    conversation_id: str,
    **overrides: object,
) -> dict:
    payload = {"conversation_id": conversation_id}
    payload.update(overrides)
    response = await client.post("/api/v1/escalations", headers=auth_headers(token), json=payload)
    assert response.status_code == 201
    return response.json()


async def test_staff_can_create_escalation_for_own_tenant_conversation(
    client: AsyncClient,
    db_session: AsyncSession,
    demo_tenants: dict[str, Tenant],
):
    staff = await create_staff_user(db_session, demo_tenants["elegant-weddings"])
    token = token_for(staff)
    conversation = await create_conversation(client, token)

    escalation = await create_escalation(client, token, conversation["id"])

    assert escalation["tenant_id"] == str(demo_tenants["elegant-weddings"].id)
    assert escalation["conversation_id"] == conversation["id"]
    assert escalation["created_by_user_id"] == str(staff.id)
    assert escalation["status"] == "open"


async def test_manager_can_create_escalation_for_own_tenant_conversation(client: AsyncClient):
    token = await login(client)
    conversation = await create_conversation(client, token)

    escalation = await create_escalation(client, token, conversation["id"])

    assert escalation["conversation_id"] == conversation["id"]
    assert escalation["status"] == "open"


async def test_user_cannot_create_escalation_for_another_tenant_conversation(client: AsyncClient):
    elegant_token = await login(client)
    royal_token = await login(
        client,
        email="admin@royal-events.demo",
        password="demo-password-2",
        tenant_slug="royal-events-agency",
    )
    royal_conversation = await create_conversation(client, royal_token, "Royal Escalation Client")

    response = await client.post(
        "/api/v1/escalations",
        headers=auth_headers(elegant_token),
        json={"conversation_id": royal_conversation["id"]},
    )

    assert response.status_code == 403


async def test_user_cannot_create_escalation_with_message_from_different_conversation(
    client: AsyncClient,
):
    token = await login(client)
    first_conversation = await create_conversation(client, token, "First Client")
    second_conversation = await create_conversation(client, token, "Second Client")
    message = await create_message(client, token, second_conversation["id"], "Second message")

    response = await client.post(
        "/api/v1/escalations",
        headers=auth_headers(token),
        json={
            "conversation_id": first_conversation["id"],
            "message_id": message["id"],
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "message does not belong to conversation"


async def test_assigned_manager_must_belong_to_same_tenant_and_have_manager_role(
    client: AsyncClient,
    db_session: AsyncSession,
    demo_tenants: dict[str, Tenant],
):
    token = await login(client)
    conversation = await create_conversation(client, token)
    staff = await create_staff_user(db_session, demo_tenants["elegant-weddings"])
    royal_manager = await get_manager_user(db_session, "admin@royal-events.demo")
    elegant_manager = await get_manager_user(db_session, "admin@elegant-weddings.demo")

    staff_response = await client.post(
        "/api/v1/escalations",
        headers=auth_headers(token),
        json={
            "conversation_id": conversation["id"],
            "assigned_manager_user_id": str(staff.id),
        },
    )
    royal_response = await client.post(
        "/api/v1/escalations",
        headers=auth_headers(token),
        json={
            "conversation_id": conversation["id"],
            "assigned_manager_user_id": str(royal_manager.id),
        },
    )
    valid_response = await client.post(
        "/api/v1/escalations",
        headers=auth_headers(token),
        json={
            "conversation_id": conversation["id"],
            "assigned_manager_user_id": str(elegant_manager.id),
        },
    )

    assert staff_response.status_code == 404
    assert royal_response.status_code == 404
    assert valid_response.status_code == 201
    assert valid_response.json()["assigned_manager_user_id"] == str(elegant_manager.id)


async def test_manager_can_list_own_tenant_escalations(client: AsyncClient):
    token = await login(client)
    conversation = await create_conversation(client, token)
    escalation = await create_escalation(client, token, conversation["id"])

    response = await client.get("/api/v1/escalations", headers=auth_headers(token))

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [escalation["id"]]


async def test_tenant_a_cannot_see_tenant_b_escalations(client: AsyncClient):
    elegant_token = await login(client)
    royal_token = await login(
        client,
        email="admin@royal-events.demo",
        password="demo-password-2",
        tenant_slug="royal-events-agency",
    )
    royal_conversation = await create_conversation(client, royal_token, "Royal Client")
    await create_escalation(client, royal_token, royal_conversation["id"])

    response = await client.get("/api/v1/escalations", headers=auth_headers(elegant_token))

    assert response.status_code == 200
    assert response.json() == []


async def test_manager_can_update_escalation_status(client: AsyncClient):
    token = await login(client)
    conversation = await create_conversation(client, token)
    escalation = await create_escalation(client, token, conversation["id"])

    response = await client.patch(
        f"/api/v1/escalations/{escalation['id']}",
        headers=auth_headers(token),
        json={"status": "in_review"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "in_review"


async def test_resolved_status_sets_resolved_at(client: AsyncClient):
    token = await login(client)
    conversation = await create_conversation(client, token)
    escalation = await create_escalation(client, token, conversation["id"])

    response = await client.patch(
        f"/api/v1/escalations/{escalation['id']}",
        headers=auth_headers(token),
        json={"status": "resolved"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "resolved"
    assert response.json()["resolved_at"] is not None


async def test_status_change_creates_audit_log(
    client: AsyncClient,
    db_session: AsyncSession,
):
    token = await login(client)
    conversation = await create_conversation(client, token)
    escalation = await create_escalation(client, token, conversation["id"])

    response = await client.patch(
        f"/api/v1/escalations/{escalation['id']}",
        headers=auth_headers(token),
        json={"status": "in_review"},
    )

    assert response.status_code == 200
    result = await db_session.execute(
        select(AuditLog).where(AuditLog.event_type == AUDIT_EVENT_ESCALATION_STATUS_CHANGED)
    )
    logs = list(result.scalars().all())
    assert len(logs) == 1
    assert logs[0].details["escalation_id"] == escalation["id"]
    assert logs[0].details["conversation_id"] == conversation["id"]
    assert logs[0].details["old_status"] == "open"
    assert logs[0].details["new_status"] == "in_review"
    assert logs[0].details["actor_user_id"] is not None


async def test_conversation_detail_includes_related_escalations(client: AsyncClient):
    token = await login(client)
    conversation = await create_conversation(client, token)
    message = await create_message(client, token, conversation["id"], "Please escalate")
    escalation = await create_escalation(client, token, conversation["id"], message_id=message["id"])

    response = await client.get(
        f"/api/v1/conversations/{conversation['id']}/detail",
        headers=auth_headers(token),
    )

    assert response.status_code == 200
    escalations = response.json()["escalations"]
    assert len(escalations) == 1
    assert escalations[0]["id"] == escalation["id"]
    assert escalations[0]["message_id"] == message["id"]


async def test_nonexistent_escalation_returns_404(client: AsyncClient):
    token = await login(client)

    response = await client.get(f"/api/v1/escalations/{uuid4()}", headers=auth_headers(token))

    assert response.status_code == 404
    assert response.json()["detail"] == "escalation not found"


async def test_cross_tenant_escalation_access_returns_403(client: AsyncClient):
    elegant_token = await login(client)
    royal_token = await login(
        client,
        email="admin@royal-events.demo",
        password="demo-password-2",
        tenant_slug="royal-events-agency",
    )
    elegant_conversation = await create_conversation(client, elegant_token, "Elegant Client")
    escalation = await create_escalation(client, elegant_token, elegant_conversation["id"])

    response = await client.get(
        f"/api/v1/escalations/{escalation['id']}",
        headers=auth_headers(royal_token),
    )

    assert response.status_code == 403
