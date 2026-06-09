from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.conversation import Conversation, ConversationStatus
from app.models.message import Message, MessageDirection, MessageStatus
from app.models.tenant import Tenant
from app.models.user import UserRole


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


async def staff_token(db_session: AsyncSession, slug: str = "elegant-weddings") -> str:
    tenant = await get_tenant(db_session, slug)
    return create_access_token(sub=uuid4(), tenant_id=tenant.id, role=UserRole.staff.value)


async def get_tenant(db_session: AsyncSession, slug: str) -> Tenant:
    result = await db_session.execute(select(Tenant).where(Tenant.slug == slug))
    return result.scalar_one()


async def create_inbox_conversation(
    db_session: AsyncSession,
    tenant: Tenant,
    *,
    client_name: str,
    body: str = "Hello from a client",
    client_contact: str | None = None,
    status: ConversationStatus = ConversationStatus.open,
    message_status: MessageStatus = MessageStatus.unread,
    sent_at: datetime | None = None,
) -> tuple[Conversation, Message]:
    sent_at = sent_at or datetime.now(timezone.utc)
    conversation = Conversation(
        tenant_id=tenant.id,
        client_name=client_name,
        client_contact=client_contact,
        status=status,
        updated_at=sent_at,
    )
    db_session.add(conversation)
    await db_session.flush()
    message = Message(
        tenant_id=tenant.id,
        conversation_id=conversation.id,
        direction=MessageDirection.inbound,
        status=message_status,
        body=body,
        source="whatsapp_simulator",
        sent_at=sent_at,
    )
    db_session.add(message)
    await db_session.commit()
    return conversation, message


async def test_staff_can_list_inbox_messages(client: AsyncClient, db_session: AsyncSession):
    token = await staff_token(db_session)
    elegant = await get_tenant(db_session, "elegant-weddings")
    conversation, _ = await create_inbox_conversation(
        db_session,
        elegant,
        client_name="Alice Johnson",
        body="Can you send me your wedding package prices?",
    )

    response = await client.get("/api/v1/inbox", headers=auth_headers(token))

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["conversation_id"] == str(conversation.id)
    assert payload["items"][0]["client_name"] == "Alice Johnson"


async def test_manager_can_list_inbox_messages(client: AsyncClient, db_session: AsyncSession):
    token = await login(client, "admin@elegant-weddings.demo", "demo-password-1")
    elegant = await get_tenant(db_session, "elegant-weddings")
    await create_inbox_conversation(db_session, elegant, client_name="Manager Client")

    response = await client.get("/api/v1/inbox", headers=auth_headers(token))

    assert response.status_code == 200
    assert response.json()["total"] == 1


async def test_inbox_item_fields_are_complete_and_correct(
    client: AsyncClient,
    db_session: AsyncSession,
):
    token = await staff_token(db_session)
    elegant = await get_tenant(db_session, "elegant-weddings")
    long_body = "x" * 120
    sent_at = datetime(2026, 6, 6, 10, 0, tzinfo=timezone.utc)
    conversation, message = await create_inbox_conversation(
        db_session,
        elegant,
        client_name="Alice Johnson",
        client_contact="+96170111222",
        body=long_body,
        sent_at=sent_at,
    )

    response = await client.get("/api/v1/inbox", headers=auth_headers(token))

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item == {
        "conversation_id": str(conversation.id),
        "latest_message_id": str(message.id),
        "client_name": "Alice Johnson",
        "client_contact": "+96170111222",
        "latest_message_preview": ("x" * 97) + "...",
        "latest_message_at": "2026-06-06T10:00:00",
        "latest_message_direction": "inbound",
        "unread_count": 1,
        "has_unread": True,
        "conversation_status": "open",
        "updated_at": "2026-06-06T10:00:00",
    }
    assert len(item["latest_message_preview"]) <= 100


async def test_inbox_empty_for_fresh_tenant(client: AsyncClient, db_session: AsyncSession):
    token = await staff_token(db_session)

    response = await client.get("/api/v1/inbox", headers=auth_headers(token))

    assert response.status_code == 200
    assert response.json() == {
        "items": [],
        "total": 0,
        "total_unread": 0,
        "page": 1,
        "page_size": 20,
        "total_pages": 0,
    }


async def test_unauthenticated_request_returns_401(client: AsyncClient):
    response = await client.get("/api/v1/inbox")

    assert response.status_code == 401
    assert response.json()["error_code"] == "MISSING_TOKEN"


async def test_invalid_token_returns_401(client: AsyncClient):
    response = await client.get("/api/v1/inbox", headers=auth_headers("not-a-valid-token"))

    assert response.status_code == 401
    assert response.json()["error_code"] == "INVALID_TOKEN"


async def test_platform_admin_blocked_from_inbox(client: AsyncClient):
    token = await login(client, "platform-admin@eventsense.demo", "platform-password")

    response = await client.get("/api/v1/inbox", headers=auth_headers(token))

    assert response.status_code == 403
    assert response.json()["error_code"] == "INSUFFICIENT_ROLE"


async def test_tenant_a_inbox_empty_for_tenant_b_user(
    client: AsyncClient,
    db_session: AsyncSession,
):
    royal_token = await staff_token(db_session, "royal-events-agency")
    elegant = await get_tenant(db_session, "elegant-weddings")
    await create_inbox_conversation(db_session, elegant, client_name="Elegant Only")

    response = await client.get("/api/v1/inbox", headers=auth_headers(royal_token))

    assert response.status_code == 200
    assert response.json()["items"] == []


async def test_newest_conversation_appears_first(client: AsyncClient, db_session: AsyncSession):
    token = await staff_token(db_session)
    elegant = await get_tenant(db_session, "elegant-weddings")
    base_time = datetime(2026, 6, 6, 10, 0, tzinfo=timezone.utc)
    older, _ = await create_inbox_conversation(
        db_session,
        elegant,
        client_name="Older Client",
        sent_at=base_time,
    )
    newer, _ = await create_inbox_conversation(
        db_session,
        elegant,
        client_name="Newer Client",
        sent_at=base_time + timedelta(hours=1),
    )

    response = await client.get("/api/v1/inbox", headers=auth_headers(token))

    assert response.status_code == 200
    assert [item["conversation_id"] for item in response.json()["items"]] == [
        str(newer.id),
        str(older.id),
    ]


async def test_unread_only_filter_excludes_read_conversations(
    client: AsyncClient,
    db_session: AsyncSession,
):
    token = await staff_token(db_session)
    elegant = await get_tenant(db_session, "elegant-weddings")
    unread, _ = await create_inbox_conversation(
        db_session,
        elegant,
        client_name="Unread Client",
        message_status=MessageStatus.unread,
    )
    await create_inbox_conversation(
        db_session,
        elegant,
        client_name="Read Client",
        message_status=MessageStatus.read,
    )

    response = await client.get(
        "/api/v1/inbox?unread_only=true",
        headers=auth_headers(token),
    )

    assert response.status_code == 200
    assert [item["conversation_id"] for item in response.json()["items"]] == [str(unread.id)]


async def test_status_filter_returns_only_matching_conversations(
    client: AsyncClient,
    db_session: AsyncSession,
):
    token = await staff_token(db_session)
    elegant = await get_tenant(db_session, "elegant-weddings")
    closed, _ = await create_inbox_conversation(
        db_session,
        elegant,
        client_name="Closed Client",
        status=ConversationStatus.closed,
    )
    await create_inbox_conversation(db_session, elegant, client_name="Open Client")

    response = await client.get("/api/v1/inbox?status=closed", headers=auth_headers(token))

    assert response.status_code == 200
    assert [item["conversation_id"] for item in response.json()["items"]] == [str(closed.id)]


async def test_combined_unread_and_status_filter(client: AsyncClient, db_session: AsyncSession):
    token = await staff_token(db_session)
    elegant = await get_tenant(db_session, "elegant-weddings")
    matching, _ = await create_inbox_conversation(
        db_session,
        elegant,
        client_name="Unread Open",
        status=ConversationStatus.open,
        message_status=MessageStatus.unread,
    )
    await create_inbox_conversation(
        db_session,
        elegant,
        client_name="Unread Closed",
        status=ConversationStatus.closed,
        message_status=MessageStatus.unread,
    )
    await create_inbox_conversation(
        db_session,
        elegant,
        client_name="Read Open",
        status=ConversationStatus.open,
        message_status=MessageStatus.read,
    )

    response = await client.get(
        "/api/v1/inbox?unread_only=true&status=open",
        headers=auth_headers(token),
    )

    assert response.status_code == 200
    assert [item["conversation_id"] for item in response.json()["items"]] == [str(matching.id)]


async def test_search_by_client_name_case_insensitive(
    client: AsyncClient,
    db_session: AsyncSession,
):
    token = await staff_token(db_session)
    elegant = await get_tenant(db_session, "elegant-weddings")
    alice, _ = await create_inbox_conversation(db_session, elegant, client_name="Alice Johnson")
    await create_inbox_conversation(db_session, elegant, client_name="Bob Smith")

    response = await client.get("/api/v1/inbox?search=alice", headers=auth_headers(token))

    assert response.status_code == 200
    assert [item["conversation_id"] for item in response.json()["items"]] == [str(alice.id)]


async def test_search_by_client_contact_and_message_body(
    client: AsyncClient,
    db_session: AsyncSession,
):
    token = await staff_token(db_session)
    elegant = await get_tenant(db_session, "elegant-weddings")
    carol, _ = await create_inbox_conversation(
        db_session,
        elegant,
        client_name="Carol Davis",
        client_contact="+96170111222",
        body="I want to cancel. Is the deposit refundable?",
    )
    await create_inbox_conversation(db_session, elegant, client_name="Bob Smith")

    body_response = await client.get(
        "/api/v1/inbox?search=deposit",
        headers=auth_headers(token),
    )
    contact_response = await client.get(
        "/api/v1/inbox?search=70111222",
        headers=auth_headers(token),
    )

    assert body_response.status_code == 200
    assert [item["conversation_id"] for item in body_response.json()["items"]] == [str(carol.id)]
    assert contact_response.status_code == 200
    assert [item["conversation_id"] for item in contact_response.json()["items"]] == [str(carol.id)]


async def test_search_and_filter_combined(client: AsyncClient, db_session: AsyncSession):
    token = await staff_token(db_session)
    elegant = await get_tenant(db_session, "elegant-weddings")
    alice, _ = await create_inbox_conversation(
        db_session,
        elegant,
        client_name="Alice Johnson",
        message_status=MessageStatus.unread,
    )
    await create_inbox_conversation(
        db_session,
        elegant,
        client_name="Alice Read",
        message_status=MessageStatus.read,
    )
    await create_inbox_conversation(db_session, elegant, client_name="Bob Smith")

    response = await client.get(
        "/api/v1/inbox?search=alice&unread_only=true",
        headers=auth_headers(token),
    )

    assert response.status_code == 200
    assert [item["conversation_id"] for item in response.json()["items"]] == [str(alice.id)]


async def test_no_match_returns_empty_items_with_tenant_wide_total_unread(
    client: AsyncClient,
    db_session: AsyncSession,
):
    token = await staff_token(db_session)
    elegant = await get_tenant(db_session, "elegant-weddings")
    await create_inbox_conversation(db_session, elegant, client_name="Unread Client")

    response = await client.get(
        "/api/v1/inbox?search=no-match",
        headers=auth_headers(token),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"] == []
    assert payload["total"] == 0
    assert payload["total_unread"] == 1


async def test_query_tenant_id_cannot_override_authenticated_tenant(
    client: AsyncClient,
    db_session: AsyncSession,
):
    elegant_token = await staff_token(db_session)
    elegant = await get_tenant(db_session, "elegant-weddings")
    royal = await get_tenant(db_session, "royal-events-agency")
    elegant_conversation, _ = await create_inbox_conversation(
        db_session,
        elegant,
        client_name="Elegant Client",
    )
    await create_inbox_conversation(db_session, royal, client_name="Royal Client")

    response = await client.get(
        f"/api/v1/inbox?tenant_id={royal.id}",
        headers=auth_headers(elegant_token),
    )

    assert response.status_code == 200
    assert [item["conversation_id"] for item in response.json()["items"]] == [
        str(elegant_conversation.id)
    ]


async def test_summary_returns_tenant_counts(client: AsyncClient, db_session: AsyncSession):
    token = await staff_token(db_session)
    elegant = await get_tenant(db_session, "elegant-weddings")
    await create_inbox_conversation(db_session, elegant, client_name="Unread One")
    await create_inbox_conversation(db_session, elegant, client_name="Unread Two")
    await create_inbox_conversation(
        db_session,
        elegant,
        client_name="Closed",
        status=ConversationStatus.closed,
        message_status=MessageStatus.read,
    )

    response = await client.get("/api/v1/inbox/summary", headers=auth_headers(token))

    assert response.status_code == 200
    assert response.json() == {
        "total_open": 2,
        "unread_or_new": 2,
        "high_risk_placeholder": 0,
    }


async def test_pagination_uses_twenty_items_per_page(
    client: AsyncClient,
    db_session: AsyncSession,
):
    token = await staff_token(db_session)
    elegant = await get_tenant(db_session, "elegant-weddings")
    base_time = datetime(2026, 6, 6, 10, 0, tzinfo=timezone.utc)
    for index in range(25):
        await create_inbox_conversation(
            db_session,
            elegant,
            client_name=f"Client {index}",
            sent_at=base_time + timedelta(minutes=index),
        )

    page_1 = await client.get("/api/v1/inbox?page=1", headers=auth_headers(token))
    page_2 = await client.get("/api/v1/inbox?page=2", headers=auth_headers(token))

    assert page_1.status_code == 200
    assert page_1.json()["total"] == 25
    assert page_1.json()["total_pages"] == 2
    assert len(page_1.json()["items"]) == 20
    assert page_2.status_code == 200
    assert len(page_2.json()["items"]) == 5


async def test_messages_created_by_simulator_appear_in_inbox(
    client: AsyncClient,
    db_session: AsyncSession,
):
    token = await staff_token(db_session)

    simulate_response = await client.post(
        "/api/v1/simulator/messages",
        headers=auth_headers(token),
        json={
            "client_name": "Maya Haddad",
            "client_contact": "+96170111222",
            "body": "Hi, can you send me your wedding package prices?",
        },
    )
    response = await client.get("/api/v1/inbox", headers=auth_headers(token))

    assert simulate_response.status_code == 201
    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["conversation_id"] == simulate_response.json()["conversation_id"]
    assert item["latest_message_id"] == simulate_response.json()["message_id"]
    assert item["has_unread"] is True
