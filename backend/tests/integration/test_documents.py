from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.audit_log import AuditLog
from app.models.tenant import Tenant
from app.models.user import User, UserRole
from app.services.audit_log_service import (
    AUDIT_EVENT_DOCUMENT_ARCHIVED,
    AUDIT_EVENT_DOCUMENT_CREATED,
    AUDIT_EVENT_DOCUMENT_UPDATED,
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


async def create_staff_token(db_session: AsyncSession, tenant: Tenant) -> str:
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
    return create_access_token(sub=staff.id, tenant_id=staff.tenant_id, role=staff.role.value)


async def create_document(
    client: AsyncClient,
    token: str,
    **overrides: object,
) -> dict:
    payload = {
        "title": "Wedding Packages 2026",
        "document_type": "package",
        "content_text": "Classic package starts with venue, decoration, and coordination.",
    }
    payload.update(overrides)
    response = await client.post("/api/v1/documents", headers=auth_headers(token), json=payload)
    assert response.status_code == 201
    return response.json()


async def test_manager_can_create_document_for_own_tenant(client: AsyncClient):
    token = await login(client)

    document = await create_document(client, token)

    assert document["title"] == "Wedding Packages 2026"
    assert document["document_type"] == "package"
    assert document["status"] == "active"
    assert document["uploaded_by_user_id"] is not None


async def test_staff_cannot_create_document(
    client: AsyncClient,
    db_session: AsyncSession,
    demo_tenants: dict[str, Tenant],
):
    token = await create_staff_token(db_session, demo_tenants["elegant-weddings"])

    response = await client.post(
        "/api/v1/documents",
        headers=auth_headers(token),
        json={
            "title": "Staff FAQ",
            "document_type": "faq",
            "content_text": "Staff should not be able to create this.",
        },
    )

    assert response.status_code == 403


async def test_staff_can_list_and_read_documents(
    client: AsyncClient,
    db_session: AsyncSession,
    demo_tenants: dict[str, Tenant],
):
    manager_token = await login(client)
    staff_token = await create_staff_token(db_session, demo_tenants["elegant-weddings"])
    document = await create_document(client, manager_token)

    list_response = await client.get("/api/v1/documents", headers=auth_headers(staff_token))
    get_response = await client.get(
        f"/api/v1/documents/{document['id']}",
        headers=auth_headers(staff_token),
    )

    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()] == [document["id"]]
    assert get_response.status_code == 200
    assert get_response.json()["id"] == document["id"]


async def test_staff_cannot_update_or_archive_document(
    client: AsyncClient,
    db_session: AsyncSession,
    demo_tenants: dict[str, Tenant],
):
    manager_token = await login(client)
    staff_token = await create_staff_token(db_session, demo_tenants["elegant-weddings"])
    document = await create_document(client, manager_token)

    update_response = await client.patch(
        f"/api/v1/documents/{document['id']}",
        headers=auth_headers(staff_token),
        json={"title": "Staff edit"},
    )
    archive_response = await client.delete(
        f"/api/v1/documents/{document['id']}",
        headers=auth_headers(staff_token),
    )

    assert update_response.status_code == 403
    assert archive_response.status_code == 403


async def test_tenant_a_cannot_view_tenant_b_document(client: AsyncClient):
    elegant_token = await login(client)
    royal_token = await login(
        client,
        email="admin@royal-events.demo",
        password="demo-password-2",
        tenant_slug="royal-events-agency",
    )
    royal_document = await create_document(client, royal_token, title="Royal Pricing")

    response = await client.get(
        f"/api/v1/documents/{royal_document['id']}",
        headers=auth_headers(elegant_token),
    )

    assert response.status_code == 403


async def test_tenant_a_cannot_update_or_archive_tenant_b_document(client: AsyncClient):
    elegant_token = await login(client)
    royal_token = await login(
        client,
        email="admin@royal-events.demo",
        password="demo-password-2",
        tenant_slug="royal-events-agency",
    )
    royal_document = await create_document(client, royal_token, title="Royal Contract")

    update_response = await client.patch(
        f"/api/v1/documents/{royal_document['id']}",
        headers=auth_headers(elegant_token),
        json={"title": "Cross tenant edit"},
    )
    archive_response = await client.delete(
        f"/api/v1/documents/{royal_document['id']}",
        headers=auth_headers(elegant_token),
    )

    assert update_response.status_code == 403
    assert archive_response.status_code == 403


async def test_list_returns_only_own_tenant_documents(client: AsyncClient):
    elegant_token = await login(client)
    royal_token = await login(
        client,
        email="admin@royal-events.demo",
        password="demo-password-2",
        tenant_slug="royal-events-agency",
    )
    elegant_document = await create_document(client, elegant_token, title="Elegant FAQ")
    await create_document(client, royal_token, title="Royal FAQ")

    response = await client.get("/api/v1/documents", headers=auth_headers(elegant_token))

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [elegant_document["id"]]


async def test_document_filters_work(client: AsyncClient):
    token = await login(client)
    pricing = await create_document(
        client,
        token,
        title="Premium Pricing",
        document_type="pricing",
        content_text="Premium hall pricing and deposit schedule.",
    )
    await create_document(
        client,
        token,
        title="Catering Rules",
        document_type="catering_rules",
        content_text="Buffet and plated dinner rules.",
        status="archived",
    )

    type_response = await client.get(
        "/api/v1/documents?document_type=pricing",
        headers=auth_headers(token),
    )
    status_response = await client.get(
        "/api/v1/documents?status=archived",
        headers=auth_headers(token),
    )
    search_response = await client.get(
        "/api/v1/documents?search=deposit",
        headers=auth_headers(token),
    )

    assert type_response.status_code == 200
    assert [item["id"] for item in type_response.json()] == [pricing["id"]]
    assert status_response.status_code == 200
    assert [item["status"] for item in status_response.json()] == ["archived"]
    assert search_response.status_code == 200
    assert [item["id"] for item in search_response.json()] == [pricing["id"]]


async def test_update_document_works(client: AsyncClient):
    token = await login(client)
    document = await create_document(client, token)

    response = await client.patch(
        f"/api/v1/documents/{document['id']}",
        headers=auth_headers(token),
        json={
            "title": "Updated Deposit Policy",
            "document_type": "deposit_policy",
            "content_text": "Deposits are due within seven days.",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Updated Deposit Policy"
    assert data["document_type"] == "deposit_policy"
    assert data["content_text"] == "Deposits are due within seven days."


async def test_delete_archives_document_instead_of_hard_deleting(client: AsyncClient):
    token = await login(client)
    document = await create_document(client, token)

    delete_response = await client.delete(
        f"/api/v1/documents/{document['id']}",
        headers=auth_headers(token),
    )
    get_response = await client.get(
        f"/api/v1/documents/{document['id']}",
        headers=auth_headers(token),
    )

    assert delete_response.status_code == 200
    assert delete_response.json()["status"] == "archived"
    assert get_response.status_code == 200
    assert get_response.json()["status"] == "archived"


async def test_audit_log_created_on_create_update_archive(
    client: AsyncClient,
    db_session: AsyncSession,
):
    token = await login(client)

    document = await create_document(client, token)
    update_response = await client.patch(
        f"/api/v1/documents/{document['id']}",
        headers=auth_headers(token),
        json={"title": "Updated Packages"},
    )
    archive_response = await client.delete(
        f"/api/v1/documents/{document['id']}",
        headers=auth_headers(token),
    )

    assert update_response.status_code == 200
    assert archive_response.status_code == 200
    result = await db_session.execute(
        select(AuditLog).where(
            AuditLog.event_type.in_(
                [
                    AUDIT_EVENT_DOCUMENT_CREATED,
                    AUDIT_EVENT_DOCUMENT_UPDATED,
                    AUDIT_EVENT_DOCUMENT_ARCHIVED,
                ]
            )
        )
    )
    logs = list(result.scalars().all())
    assert {log.event_type for log in logs} == {
        AUDIT_EVENT_DOCUMENT_CREATED,
        AUDIT_EVENT_DOCUMENT_UPDATED,
        AUDIT_EVENT_DOCUMENT_ARCHIVED,
    }
    archived_log = next(log for log in logs if log.event_type == AUDIT_EVENT_DOCUMENT_ARCHIVED)
    assert archived_log.details["document_id"] == document["id"]
    assert archived_log.details["title"] == "Updated Packages"
    assert archived_log.details["old_status"] == "active"
    assert archived_log.details["new_status"] == "archived"


async def test_nonexistent_document_returns_404(client: AsyncClient):
    token = await login(client)

    response = await client.get(f"/api/v1/documents/{uuid4()}", headers=auth_headers(token))

    assert response.status_code == 404
    assert response.json()["detail"] == "document not found"


async def test_archived_documents_are_visible_by_default_and_with_status_filter(
    client: AsyncClient,
):
    token = await login(client)
    document = await create_document(client, token)
    archive_response = await client.delete(
        f"/api/v1/documents/{document['id']}",
        headers=auth_headers(token),
    )

    default_response = await client.get("/api/v1/documents", headers=auth_headers(token))
    archived_response = await client.get(
        "/api/v1/documents?status=archived",
        headers=auth_headers(token),
    )

    assert archive_response.status_code == 200
    assert [item["id"] for item in default_response.json()] == [document["id"]]
    assert [item["id"] for item in archived_response.json()] == [document["id"]]


async def test_empty_title_or_content_is_rejected(client: AsyncClient):
    token = await login(client)

    title_response = await client.post(
        "/api/v1/documents",
        headers=auth_headers(token),
        json={"title": " ", "document_type": "faq", "content_text": "Useful FAQ"},
    )
    content_response = await client.post(
        "/api/v1/documents",
        headers=auth_headers(token),
        json={"title": "Useful FAQ", "document_type": "faq", "content_text": " "},
    )

    assert title_response.status_code == 422
    assert content_response.status_code == 422
