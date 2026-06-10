from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.audit_log import AuditLog
from app.models.tenant import Tenant
from app.models.user import User, UserRole
from app.services.audit_log_service import AUDIT_EVENT_TASK_STATUS_CHANGED


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


async def create_staff_token(db_session: AsyncSession, tenant: Tenant) -> str:
    staff = User(
        tenant_id=tenant.id,
        email="staff@elegant-weddings.demo",
        hashed_password=hash_password("staff-password"),
        role=UserRole.staff,
        full_name="Elegant Staff",
    )
    db_session.add(staff)
    await db_session.commit()
    await db_session.refresh(staff)
    return create_access_token(sub=staff.id, tenant_id=staff.tenant_id, role=staff.role.value)


async def create_conversation(client: AsyncClient, token: str, client_name: str = "Task Client") -> dict:
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


async def create_task(
    client: AsyncClient,
    token: str,
    conversation_id: str,
    **overrides: object,
) -> dict:
    payload = {
        "conversation_id": conversation_id,
        "title": "Follow up with client",
        "description": "Confirm package details",
    }
    payload.update(overrides)
    response = await client.post("/api/v1/tasks", headers=auth_headers(token), json=payload)
    assert response.status_code == 201
    return response.json()


async def test_staff_can_create_task_for_own_tenant_conversation(
    client: AsyncClient,
    db_session: AsyncSession,
    demo_tenants: dict[str, Tenant],
):
    token = await create_staff_token(db_session, demo_tenants["elegant-weddings"])
    conversation = await create_conversation(client, token)

    task = await create_task(client, token, conversation["id"])

    assert task["tenant_id"] == str(demo_tenants["elegant-weddings"].id)
    assert task["conversation_id"] == conversation["id"]
    assert task["status"] == "open"


async def test_manager_can_create_task_for_own_tenant_conversation(client: AsyncClient):
    token = await login(client)
    conversation = await create_conversation(client, token)

    task = await create_task(client, token, conversation["id"], title="Manager follow-up")

    assert task["title"] == "Manager follow-up"
    assert task["conversation_id"] == conversation["id"]


async def test_user_cannot_create_task_for_another_tenant_conversation(client: AsyncClient):
    elegant_token = await login(client)
    royal_token = await login(
        client,
        email="admin@royal-events.demo",
        password="demo-password-2",
        tenant_slug="royal-events-agency",
    )
    royal_conversation = await create_conversation(client, royal_token, "Royal Task Client")

    response = await client.post(
        "/api/v1/tasks",
        headers=auth_headers(elegant_token),
        json={"conversation_id": royal_conversation["id"], "title": "Cross tenant task"},
    )

    assert response.status_code == 403


async def test_user_cannot_create_task_with_message_from_different_conversation(
    client: AsyncClient,
):
    token = await login(client)
    first_conversation = await create_conversation(client, token, "First Client")
    second_conversation = await create_conversation(client, token, "Second Client")
    message = await create_message(client, token, second_conversation["id"], "Second message")

    response = await client.post(
        "/api/v1/tasks",
        headers=auth_headers(token),
        json={
            "conversation_id": first_conversation["id"],
            "message_id": message["id"],
            "title": "Wrong message task",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "message does not belong to conversation"


async def test_user_can_list_only_own_tenant_tasks(client: AsyncClient):
    elegant_token = await login(client)
    royal_token = await login(
        client,
        email="admin@royal-events.demo",
        password="demo-password-2",
        tenant_slug="royal-events-agency",
    )
    elegant_conversation = await create_conversation(client, elegant_token, "Elegant Client")
    royal_conversation = await create_conversation(client, royal_token, "Royal Client")
    elegant_task = await create_task(client, elegant_token, elegant_conversation["id"])
    await create_task(client, royal_token, royal_conversation["id"], title="Royal task")

    response = await client.get("/api/v1/tasks", headers=auth_headers(elegant_token))

    assert response.status_code == 200
    tasks = response.json()
    assert [task["id"] for task in tasks] == [elegant_task["id"]]


async def test_user_can_update_task_status(client: AsyncClient):
    token = await login(client)
    conversation = await create_conversation(client, token)
    task = await create_task(client, token, conversation["id"])

    response = await client.patch(
        f"/api/v1/tasks/{task['id']}",
        headers=auth_headers(token),
        json={"status": "completed"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "completed"


async def test_status_change_creates_audit_log(
    client: AsyncClient,
    db_session: AsyncSession,
):
    token = await login(client)
    conversation = await create_conversation(client, token)
    task = await create_task(client, token, conversation["id"])

    response = await client.patch(
        f"/api/v1/tasks/{task['id']}",
        headers=auth_headers(token),
        json={"status": "in_progress"},
    )

    assert response.status_code == 200
    result = await db_session.execute(
        select(AuditLog).where(AuditLog.event_type == AUDIT_EVENT_TASK_STATUS_CHANGED)
    )
    logs = list(result.scalars().all())
    assert len(logs) == 1
    assert logs[0].details["task_id"] == task["id"]
    assert logs[0].details["conversation_id"] == conversation["id"]
    assert logs[0].details["old_status"] == "open"
    assert logs[0].details["new_status"] == "in_progress"
    assert logs[0].details["actor_user_id"] is not None


async def test_conversation_detail_includes_related_tasks(client: AsyncClient):
    token = await login(client)
    conversation = await create_conversation(client, token)
    message = await create_message(client, token, conversation["id"], "Please follow up")
    task = await create_task(client, token, conversation["id"], message_id=message["id"])

    response = await client.get(
        f"/api/v1/conversations/{conversation['id']}/detail",
        headers=auth_headers(token),
    )

    assert response.status_code == 200
    tasks = response.json()["tasks"]
    assert len(tasks) == 1
    assert tasks[0]["id"] == task["id"]
    assert tasks[0]["message_id"] == message["id"]


async def test_nonexistent_task_returns_404(client: AsyncClient):
    token = await login(client)

    response = await client.get(f"/api/v1/tasks/{uuid4()}", headers=auth_headers(token))

    assert response.status_code == 404
    assert response.json()["detail"] == "task not found"


async def test_cross_tenant_task_access_returns_403(client: AsyncClient):
    elegant_token = await login(client)
    royal_token = await login(
        client,
        email="admin@royal-events.demo",
        password="demo-password-2",
        tenant_slug="royal-events-agency",
    )
    elegant_conversation = await create_conversation(client, elegant_token, "Elegant Client")
    task = await create_task(client, elegant_token, elegant_conversation["id"])

    response = await client.get(f"/api/v1/tasks/{task['id']}", headers=auth_headers(royal_token))

    assert response.status_code == 403
