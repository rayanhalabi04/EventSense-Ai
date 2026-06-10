from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.audit_log import AuditLog
from app.models.tenant import Tenant
from app.models.user import User, UserRole
from app.services.audit_log_service import (
    AUDIT_EVENT_AUTH_LOGIN_SUCCESS,
    AUDIT_EVENT_SIMULATOR_MESSAGE_RECEIVED,
    AUDIT_EVENT_TENANT_CROSS_TENANT_ACCESS_BLOCKED,
)


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


async def user_by_email(db_session: AsyncSession, email: str) -> User:
    return (await db_session.execute(select(User).where(User.email == email))).scalar_one()


async def tenant_by_slug(db_session: AsyncSession, slug: str) -> Tenant:
    return (await db_session.execute(select(Tenant).where(Tenant.slug == slug))).scalar_one()


async def audit_logs_for_event(db_session: AsyncSession, event_type: str) -> list[AuditLog]:
    result = await db_session.execute(select(AuditLog).where(AuditLog.event_type == event_type))
    return list(result.scalars().all())


async def test_audit_log_created_on_simulator_message(
    client: AsyncClient,
    db_session: AsyncSession,
):
    token = await login(client)

    response = await client.post(
        "/api/v1/simulator/messages",
        headers=auth_headers(token),
        json={"client_name": "Audit Client", "body": "Please send pricing"},
    )

    assert response.status_code == 201
    logs = await audit_logs_for_event(db_session, AUDIT_EVENT_SIMULATOR_MESSAGE_RECEIVED)
    assert len(logs) == 1
    assert logs[0].tenant_id == UUID(response.json()["tenant_id"])
    assert logs[0].resource_type == "message"
    assert logs[0].resource_id == response.json()["message_id"]
    assert logs[0].details["conversation_id"] == response.json()["conversation_id"]


async def test_audit_log_created_on_login_success(
    client: AsyncClient,
    db_session: AsyncSession,
):
    await login(client)
    user = await user_by_email(db_session, "admin@elegant-weddings.demo")

    logs = await audit_logs_for_event(db_session, AUDIT_EVENT_AUTH_LOGIN_SUCCESS)

    assert len(logs) == 1
    assert logs[0].tenant_id == user.tenant_id
    assert logs[0].actor_user_id == user.id
    assert logs[0].details["role"] == UserRole.manager.value


async def test_cross_tenant_blocked_access_creates_audit_log(
    client: AsyncClient,
    db_session: AsyncSession,
):
    elegant_token = await login(client)
    royal_token = await login(
        client,
        email="admin@royal-events.demo",
        password="demo-password-2",
        tenant_slug="royal-events-agency",
    )
    create_response = await client.post(
        "/api/v1/simulator/messages",
        headers=auth_headers(elegant_token),
        json={"client_name": "Elegant Audit Client", "body": "Elegant-only message"},
    )

    response = await client.post(
        "/api/v1/simulator/messages",
        headers=auth_headers(royal_token),
        json={
            "conversation_id": create_response.json()["conversation_id"],
            "body": "Cross-tenant attempt",
        },
    )

    assert response.status_code == 403
    royal = await tenant_by_slug(db_session, "royal-events-agency")
    logs = await audit_logs_for_event(
        db_session,
        AUDIT_EVENT_TENANT_CROSS_TENANT_ACCESS_BLOCKED,
    )
    assert len(logs) == 1
    assert logs[0].tenant_id == royal.id
    assert logs[0].resource_type == "conversation"
    assert logs[0].resource_id == create_response.json()["conversation_id"]


async def test_tenant_a_cannot_see_tenant_b_audit_logs(
    client: AsyncClient,
    db_session: AsyncSession,
):
    elegant_token = await login(client)
    royal_token = await login(
        client,
        email="admin@royal-events.demo",
        password="demo-password-2",
        tenant_slug="royal-events-agency",
    )
    royal_message = await client.post(
        "/api/v1/simulator/messages",
        headers=auth_headers(royal_token),
        json={"client_name": "Royal Audit Client", "body": "Royal-only message"},
    )

    response = await client.get("/api/v1/audit-logs", headers=auth_headers(elegant_token))

    assert response.status_code == 200
    elegant = await tenant_by_slug(db_session, "elegant-weddings")
    assert all(item["tenant_id"] == str(elegant.id) for item in response.json())
    assert royal_message.json()["message_id"] not in {
        item["resource_id"] for item in response.json()
    }


async def test_audit_log_role_permissions_respected(
    client: AsyncClient,
    db_session: AsyncSession,
):
    tenant = await tenant_by_slug(db_session, "elegant-weddings")
    staff = User(
        tenant_id=tenant.id,
        email="audit-staff@elegant-weddings.demo",
        hashed_password=hash_password("staff-password-1"),
        role=UserRole.staff,
        full_name="Audit Staff",
    )
    db_session.add(staff)
    await db_session.commit()
    manager = await user_by_email(db_session, "admin@elegant-weddings.demo")
    staff_token = create_access_token(
        sub=staff.id,
        tenant_id=staff.tenant_id,
        role=staff.role.value,
    )
    manager_token = create_access_token(
        sub=manager.id,
        tenant_id=manager.tenant_id,
        role=manager.role.value,
    )

    staff_response = await client.get(
        "/api/v1/audit-logs",
        headers=auth_headers(staff_token),
    )
    manager_response = await client.get(
        "/api/v1/audit-logs",
        headers=auth_headers(manager_token),
    )

    assert staff_response.status_code == 403
    assert staff_response.json()["error_code"] == "INSUFFICIENT_ROLE"
    assert manager_response.status_code == 200
