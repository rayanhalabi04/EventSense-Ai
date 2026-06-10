import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.services.audit_log_service import (
    AUDIT_EVENT_SUGGESTED_REPLY_APPROVED,
    AUDIT_EVENT_SUGGESTED_REPLY_EDITED,
    AUDIT_EVENT_SUGGESTED_REPLY_GENERATED,
    AUDIT_EVENT_SUGGESTED_REPLY_REFUSED_NO_SOURCE,
    AUDIT_EVENT_SUGGESTED_REPLY_REJECTED,
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


async def login_royal(client: AsyncClient) -> str:
    return await login(
        client,
        email="admin@royal-events.demo",
        password="demo-password-2",
        tenant_slug="royal-events-agency",
    )


async def create_document(
    client: AsyncClient,
    token: str,
    *,
    title: str,
    document_type: str,
    content_text: str,
) -> dict[str, object]:
    response = await client.post(
        "/api/v1/documents",
        headers=auth_headers(token),
        json={"title": title, "document_type": document_type, "content_text": content_text},
    )
    assert response.status_code == 201
    return response.json()


async def create_simulator_message(
    client: AsyncClient,
    token: str,
    *,
    body: str,
    client_name: str = "Suggested Reply Client",
    client_contact: str = "+96170100200",
) -> dict[str, object]:
    response = await client.post(
        "/api/v1/simulator/messages",
        headers=auth_headers(token),
        json={"client_name": client_name, "client_contact": client_contact, "body": body},
    )
    assert response.status_code == 201
    return response.json()


async def generate_reply(
    client: AsyncClient,
    token: str,
    conversation_id: str,
) -> dict[str, object]:
    response = await client.post(
        f"/api/v1/conversations/{conversation_id}/suggested-reply",
        headers=auth_headers(token),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def audit_events(db_session: AsyncSession, event_type: str) -> list[AuditLog]:
    result = await db_session.execute(select(AuditLog).where(AuditLog.event_type == event_type))
    return list(result.scalars().all())


async def test_generate_reply_for_elegant_deposit_question(
    client: AsyncClient,
    db_session: AsyncSession,
):
    token = await login(client)
    document = await create_document(
        client,
        token,
        title="Elegant Deposit Policy",
        document_type="deposit_policy",
        content_text=(
            "The booking deposit reserves your wedding date. The booking deposit is "
            "non-refundable after booking confirmation because it secures our planning team."
        ),
    )
    simulated = await create_simulator_message(
        client, token, body="Is the deposit refundable after booking confirmation?"
    )

    reply = await generate_reply(client, token, simulated["conversation_id"])

    assert reply["answer_supported"] is True
    assert reply["status"] == "draft"
    assert "non-refundable after booking confirmation" in reply["suggested_text"].lower()
    assert reply["source_document_ids"] == [document["id"]]
    assert all(source["document_id"] == document["id"] for source in reply["rag_sources"])
    # The generated audit event records the answering document.
    events = await audit_events(db_session, AUDIT_EVENT_SUGGESTED_REPLY_GENERATED)
    assert any(e.details.get("suggested_reply_id") == reply["id"] for e in events)


async def test_generate_reply_for_royal_refund_question(
    client: AsyncClient,
):
    royal_token = await login_royal(client)
    document = await create_document(
        client,
        royal_token,
        title="Royal Deposit Policy",
        document_type="deposit_policy",
        content_text=(
            "The deposit is partially refundable if cancellation happens more than 30 days "
            "before the event, subject to manager review of committed production costs."
        ),
    )
    simulated = await create_simulator_message(
        client, royal_token, body="Is my deposit partially refundable if I cancel?"
    )

    reply = await generate_reply(client, royal_token, simulated["conversation_id"])

    text = reply["suggested_text"].lower()
    assert reply["answer_supported"] is True
    assert "partially refundable" in text
    assert "30 days" in text
    assert reply["source_document_ids"] == [document["id"]]
    assert all(source["document_id"] == document["id"] for source in reply["rag_sources"])


async def test_no_source_reply_refuses_without_inventing_policy(
    client: AsyncClient,
    db_session: AsyncSession,
):
    token = await login(client)
    await create_document(
        client,
        token,
        title="Pricing Sheet",
        document_type="pricing",
        content_text="The classic package includes coordination and decor.",
    )
    simulated = await create_simulator_message(
        client, token, body="Can you book my honeymoon flight?"
    )

    reply = await generate_reply(client, token, simulated["conversation_id"])

    text = reply["suggested_text"].lower()
    assert reply["answer_supported"] is False
    assert reply["refusal_reason"] is not None
    assert reply["source_document_ids"] == []
    assert reply["rag_sources"] == []
    assert "could not find enough information" in text
    assert "uploaded company documents" in text
    # No invented policy facts should appear in a refusal.
    assert "refundable" not in text
    assert "deposit" not in text

    events = await audit_events(db_session, AUDIT_EVENT_SUGGESTED_REPLY_REFUSED_NO_SOURCE)
    assert any(e.details.get("suggested_reply_id") == reply["id"] for e in events)


async def test_honeymoon_flight_question_refuses_even_with_transport_faq(
    client: AsyncClient,
):
    token = await login(client)
    await create_document(
        client,
        token,
        title="Elegant Services FAQ",
        document_type="faq",
        content_text=(
            "The agency does not provide guest airport transportation unless it is "
            "added as a custom service. The booking deposit is non-refundable after "
            "booking confirmation."
        ),
    )
    simulated = await create_simulator_message(
        client, token, body="Can you book my honeymoon flight?"
    )

    reply = await generate_reply(client, token, simulated["conversation_id"])

    text = reply["suggested_text"].lower()
    assert reply["answer_supported"] is False
    assert reply["rag_sources"] == []
    assert "could not find enough information" in text
    assert "deposit" not in text
    assert "non-refundable" not in text


async def test_high_risk_cancellation_reply_includes_escalation_wording(
    client: AsyncClient,
):
    token = await login(client)
    await create_document(
        client,
        token,
        title="Elegant Cancellation Policy",
        document_type="cancellation_policy",
        content_text=(
            "Cancellations made more than 30 days before the event may receive a partial "
            "refund, subject to manager review. Within 30 days the booking is non-refundable."
        ),
    )
    simulated = await create_simulator_message(
        client, token, body="I want to cancel my wedding and get a refund."
    )

    reply = await generate_reply(client, token, simulated["conversation_id"])

    text = reply["suggested_text"].lower()
    assert reply["answer_supported"] is True
    assert "manager" in text
    assert "escalate" in text


async def test_conversation_detail_includes_latest_suggested_reply(
    client: AsyncClient,
):
    token = await login(client)
    await create_document(
        client,
        token,
        title="Elegant Deposit Policy",
        document_type="deposit_policy",
        content_text="The booking deposit is non-refundable after booking confirmation.",
    )
    simulated = await create_simulator_message(
        client, token, body="Is the deposit refundable after booking confirmation?"
    )
    reply = await generate_reply(client, token, simulated["conversation_id"])

    response = await client.get(
        f"/api/v1/conversations/{simulated['conversation_id']}/detail",
        headers=auth_headers(token),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["suggested_reply"] is not None
    assert data["suggested_reply"]["id"] == reply["id"]
    assert data["suggested_reply"]["suggested_text"] == reply["suggested_text"]
    assert data["rag_sources"]
    assert data["rag_sources"][0]["document_id"] == reply["rag_sources"][0]["document_id"]


async def test_list_and_get_suggested_replies(
    client: AsyncClient,
):
    token = await login(client)
    await create_document(
        client,
        token,
        title="Elegant Guest Count Deadline",
        document_type="faq",
        content_text="Final guest count is due 10 days before event.",
    )
    simulated = await create_simulator_message(
        client, token, body="When is the final guest count due?"
    )
    reply = await generate_reply(client, token, simulated["conversation_id"])

    list_response = await client.get(
        f"/api/v1/conversations/{simulated['conversation_id']}/suggested-replies",
        headers=auth_headers(token),
    )
    assert list_response.status_code == 200
    assert list_response.json()[0]["id"] == reply["id"]

    get_response = await client.get(
        f"/api/v1/suggested-replies/{reply['id']}",
        headers=auth_headers(token),
    )
    assert get_response.status_code == 200
    assert get_response.json()["id"] == reply["id"]
    assert "10 days before event" in get_response.json()["suggested_text"]


async def test_update_reply_status_transitions(
    client: AsyncClient,
    db_session: AsyncSession,
):
    token = await login(client)
    await create_document(
        client,
        token,
        title="Elegant Deposit Policy",
        document_type="deposit_policy",
        content_text="The booking deposit is non-refundable after booking confirmation.",
    )
    simulated = await create_simulator_message(
        client, token, body="Is the deposit refundable after booking confirmation?"
    )
    reply = await generate_reply(client, token, simulated["conversation_id"])

    approve = await client.patch(
        f"/api/v1/suggested-replies/{reply['id']}",
        headers=auth_headers(token),
        json={"status": "approved"},
    )
    assert approve.status_code == 200
    assert approve.json()["status"] == "approved"
    assert approve.json()["approved_by_user_id"] is not None

    edit = await client.patch(
        f"/api/v1/suggested-replies/{reply['id']}",
        headers=auth_headers(token),
        json={"suggested_text": "Hi! Our deposit is non-refundable after confirmation."},
    )
    assert edit.status_code == 200
    assert edit.json()["status"] == "edited"
    assert edit.json()["suggested_text"].startswith("Hi! Our deposit")

    reject = await client.patch(
        f"/api/v1/suggested-replies/{reply['id']}",
        headers=auth_headers(token),
        json={"status": "rejected"},
    )
    assert reject.status_code == 200
    assert reject.json()["status"] == "rejected"

    approved_events = await audit_events(db_session, AUDIT_EVENT_SUGGESTED_REPLY_APPROVED)
    edited_events = await audit_events(db_session, AUDIT_EVENT_SUGGESTED_REPLY_EDITED)
    rejected_events = await audit_events(db_session, AUDIT_EVENT_SUGGESTED_REPLY_REJECTED)
    assert any(e.details.get("suggested_reply_id") == reply["id"] for e in approved_events)
    assert any(e.details.get("suggested_reply_id") == reply["id"] for e in edited_events)
    assert any(e.details.get("suggested_reply_id") == reply["id"] for e in rejected_events)


async def test_cross_tenant_access_is_blocked(
    client: AsyncClient,
):
    elegant_token = await login(client)
    royal_token = await login_royal(client)

    await create_document(
        client,
        elegant_token,
        title="Elegant Deposit Policy",
        document_type="deposit_policy",
        content_text="The booking deposit is non-refundable after booking confirmation.",
    )
    simulated = await create_simulator_message(
        client, elegant_token, body="Is the deposit refundable after booking confirmation?"
    )
    conversation_id = simulated["conversation_id"]

    # Tenant B cannot generate a reply for Tenant A's conversation.
    forbidden_generate = await client.post(
        f"/api/v1/conversations/{conversation_id}/suggested-reply",
        headers=auth_headers(royal_token),
    )
    assert forbidden_generate.status_code == 403

    # Tenant B cannot list Tenant A's suggested replies.
    forbidden_list = await client.get(
        f"/api/v1/conversations/{conversation_id}/suggested-replies",
        headers=auth_headers(royal_token),
    )
    assert forbidden_list.status_code == 403

    # Tenant A generates a reply; Tenant B cannot update it.
    reply = await generate_reply(client, elegant_token, conversation_id)
    forbidden_update = await client.patch(
        f"/api/v1/suggested-replies/{reply['id']}",
        headers=auth_headers(royal_token),
        json={"status": "approved"},
    )
    assert forbidden_update.status_code == 403

    forbidden_get = await client.get(
        f"/api/v1/suggested-replies/{reply['id']}",
        headers=auth_headers(royal_token),
    )
    assert forbidden_get.status_code == 403


async def test_explicit_message_id_must_be_inbound(client: AsyncClient):
    token = await login(client)
    await create_document(
        client,
        token,
        title="Elegant Deposit Policy",
        document_type="deposit_policy",
        content_text="The booking deposit is non-refundable after booking confirmation.",
    )
    simulated = await create_simulator_message(
        client, token, body="Is the deposit refundable after booking confirmation?"
    )
    outbound = await client.post(
        f"/api/v1/conversations/{simulated['conversation_id']}/messages",
        headers=auth_headers(token),
        json={"body": "Staff draft only.", "direction": "outbound"},
    )
    assert outbound.status_code == 201

    response = await client.post(
        f"/api/v1/conversations/{simulated['conversation_id']}/suggested-reply",
        headers=auth_headers(token),
        json={"message_id": outbound.json()["id"]},
    )
    assert response.status_code == 400
    assert "inbound" in response.json()["detail"]


async def test_suggested_reply_endpoints_require_auth(client: AsyncClient):
    token = await login(client)
    await create_document(
        client,
        token,
        title="Elegant Deposit Policy",
        document_type="deposit_policy",
        content_text="The booking deposit is non-refundable after booking confirmation.",
    )
    simulated = await create_simulator_message(
        client, token, body="Is the deposit refundable after booking confirmation?"
    )
    reply = await generate_reply(client, token, simulated["conversation_id"])

    generate_response = await client.post(
        f"/api/v1/conversations/{simulated['conversation_id']}/suggested-reply"
    )
    list_response = await client.get(
        f"/api/v1/conversations/{simulated['conversation_id']}/suggested-replies"
    )
    get_response = await client.get(f"/api/v1/suggested-replies/{reply['id']}")
    patch_response = await client.patch(
        f"/api/v1/suggested-replies/{reply['id']}",
        json={"status": "approved"},
    )

    assert generate_response.status_code == 401
    assert list_response.status_code == 401
    assert get_response.status_code == 401
    assert patch_response.status_code == 401
