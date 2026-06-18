import io
import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse

import pytest
from httpx import AsyncClient
from jose import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.calendar import get_google_calendar_service
from app.core.calendar_crypto import decrypt_calendar_token
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models.audit_log import AuditLog
from app.models.calendar import CalendarConnection, CalendarEvent
from app.models.tenant import Tenant
from app.models.user import User, UserRole
from app.services.calendar_service import (
    AUDIT_EVENT_CALENDAR_AVAILABILITY_CHECKED,
    AUDIT_EVENT_CALENDAR_CONNECTED,
    AUDIT_EVENT_CALENDAR_CONNECTION_FAILED,
    AUDIT_EVENT_CALENDAR_EVENT_CREATED,
)
from app.services.google_calendar_service import (
    GoogleCalendarBusyEvent,
    GoogleCalendarOAuthError,
    GoogleCalendarService,
    GoogleEventResult,
    GoogleTokenBundle,
)


pytestmark = pytest.mark.asyncio


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class FakeGoogleCalendarService:
    def __init__(self) -> None:
        self.created_events: list[dict[str, object]] = []
        self.busy_events: list[GoogleCalendarBusyEvent] = []

    def build_authorization_url(self, *, state: str) -> str:
        return f"https://accounts.google.test/o/oauth2/auth?state={state}"

    def exchange_code_for_tokens(self, *, code: str, state: str | None = None) -> GoogleTokenBundle:
        return GoogleTokenBundle(
            access_token="test-access-token",
            refresh_token="test-refresh-token",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            scopes="https://www.googleapis.com/auth/calendar.events",
            provider_account_email="elegantweddings12@gmail.com",
        )

    def encrypt_access_token(self, token: str) -> str:
        from app.core.calendar_crypto import encrypt_calendar_token

        return encrypt_calendar_token(token)

    def encrypt_refresh_token(self, token: str) -> str:
        from app.core.calendar_crypto import encrypt_calendar_token

        return encrypt_calendar_token(token)

    def create_event(self, **kwargs: object) -> GoogleEventResult:
        self.created_events.append(kwargs)
        return GoogleEventResult(
            provider_event_id="google-event-123",
            provider_event_link="https://calendar.google.test/event?eid=123",
        )

    def delete_event(self, **kwargs: object) -> None:
        return None

    def list_events_between(self, **kwargs: object) -> list[GoogleCalendarBusyEvent]:
        start_time = kwargs["start_time"]
        end_time = kwargs["end_time"]
        return [
            event
            for event in self.busy_events
            if event.start_time < end_time and event.end_time > start_time
        ]


class MissingRefreshTokenGoogleCalendarService(FakeGoogleCalendarService):
    def exchange_code_for_tokens(self, *, code: str, state: str | None = None) -> GoogleTokenBundle:
        raise RuntimeError(
            "Google did not return a refresh token. Remove app access from Google Account and reconnect."
        )


@pytest.fixture
def calendar_settings(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app.services.calendar_service.settings.google_calendar_enabled", True)
    monkeypatch.setattr("app.services.calendar_service.settings.google_client_id", "client-id")
    monkeypatch.setattr("app.services.calendar_service.settings.google_client_secret", "client-secret")
    monkeypatch.setattr("app.core.calendar_crypto.settings.calendar_token_encryption_key", "test-calendar-secret")
    monkeypatch.setattr("app.services.calendar_service.settings.calendar_token_encryption_key", "test-calendar-secret")
    yield


@pytest.fixture
def fake_google() -> FakeGoogleCalendarService:
    fake = FakeGoogleCalendarService()
    app.dependency_overrides[get_google_calendar_service] = lambda: fake
    return fake


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
        email="calendar-staff@elegant-weddings.demo",
        hashed_password=hash_password("staff-password"),
        role=UserRole.staff,
        full_name="Calendar Staff",
    )
    db_session.add(staff)
    await db_session.commit()
    await db_session.refresh(staff)
    return create_access_token(sub=staff.id, tenant_id=staff.tenant_id, role=staff.role.value)


async def tenant_by_slug(db_session: AsyncSession, slug: str) -> Tenant:
    return (await db_session.execute(select(Tenant).where(Tenant.slug == slug))).scalar_one()


async def create_conversation(client: AsyncClient, token: str, client_name: str = "Calendar Client") -> dict:
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


async def connect_calendar(client: AsyncClient, token: str) -> None:
    connect_response = await client.get(
        "/api/v1/integrations/calendar/google/connect",
        headers=auth_headers(token),
    )
    assert connect_response.status_code == 200
    state = parse_qs(urlparse(connect_response.json()["authorization_url"]).query)["state"][0]

    callback_response = await client.get(
        "/api/v1/integrations/calendar/google/callback",
        params={"code": "auth-code", "state": state},
        follow_redirects=False,
    )
    assert callback_response.status_code == 307
    assert callback_response.headers["location"].endswith("/settings?calendar=connected")


async def test_calendar_status_when_not_connected(
    client: AsyncClient,
    calendar_settings,
    fake_google: FakeGoogleCalendarService,
):
    token = await login(client)

    response = await client.get("/api/v1/integrations/calendar/status", headers=auth_headers(token))

    assert response.status_code == 200
    assert response.json() == {
        "connected": False,
        "provider": None,
        "provider_account_email": None,
        "calendar_id": None,
        "connection_type": None,
    }


async def test_manager_can_start_connect_flow(
    client: AsyncClient,
    calendar_settings,
    fake_google: FakeGoogleCalendarService,
):
    token = await login(client)

    response = await client.get(
        "/api/v1/integrations/calendar/google/connect",
        headers=auth_headers(token),
    )

    assert response.status_code == 200
    assert response.json()["authorization_url"].startswith("https://accounts.google.test/")


async def test_google_authorization_url_uses_offline_consent_and_redirect_uri(
    calendar_settings,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    monkeypatch.setattr("app.services.google_calendar_service.settings.google_client_id", "client-id")
    monkeypatch.setattr("app.services.google_calendar_service.settings.google_client_secret", "client-secret")
    monkeypatch.setattr(
        "app.services.google_calendar_service.settings.google_redirect_uri",
        "http://localhost:8088/api/v1/integrations/calendar/google/callback",
    )
    monkeypatch.setattr(
        "app.services.google_calendar_service.settings.google_calendar_scopes",
        "openid email profile https://www.googleapis.com/auth/calendar.events",
    )
    caplog.set_level(logging.DEBUG, logger="app.services.google_calendar_service")

    authorization_url = GoogleCalendarService().build_authorization_url(state="safe-state")
    query = parse_qs(urlparse(authorization_url).query)

    assert authorization_url.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert query["client_id"] == ["client-id"]
    assert query["access_type"] == ["offline"]
    assert query["prompt"] == ["consent"]
    assert query["include_granted_scopes"] == ["true"]
    assert query["response_type"] == ["code"]
    assert query["scope"] == ["openid email profile https://www.googleapis.com/auth/calendar.events"]
    assert query["state"] == ["safe-state"]
    assert query["redirect_uri"] == [
        "http://localhost:8088/api/v1/integrations/calendar/google/callback"
    ]
    assert "code_challenge" not in query
    assert "code_challenge_method" not in query
    assert "redirect_uri=http://localhost:8088/api/v1/integrations/calendar/google/callback" in caplog.text
    assert "access_type=offline" in caplog.text
    assert "prompt=consent" in caplog.text
    assert "include_granted_scopes=true" in caplog.text
    assert "client-secret" not in caplog.text


async def test_google_token_exchange_posts_confidential_form_without_code_verifier(
    calendar_settings,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr("app.services.google_calendar_service.settings.google_client_id", "client-id")
    monkeypatch.setattr("app.services.google_calendar_service.settings.google_client_secret", "client-secret")
    monkeypatch.setattr(
        "app.services.google_calendar_service.settings.google_redirect_uri",
        "http://localhost:8088/api/v1/integrations/calendar/google/callback",
    )
    monkeypatch.setattr(
        "app.services.google_calendar_service.settings.google_calendar_scopes",
        "openid email profile https://www.googleapis.com/auth/calendar.events",
    )

    id_token = jwt.encode(
        {"email": "elegantweddings12@gmail.com"},
        "not-used-for-verification",
        algorithm="HS256",
    )
    captured_requests: list[object] = []

    class TokenResponse:
        status = 200

        def __enter__(self) -> "TokenResponse":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return (
                '{"access_token":"test-access-token","refresh_token":"test-refresh-token",'
                '"expires_in":3600,"scope":"openid email profile '
                'https://www.googleapis.com/auth/calendar.events","token_type":"Bearer",'
                f'"id_token":"{id_token}"'
                "}"
            ).encode("utf-8")

    def fake_urlopen(request: object, timeout: int) -> TokenResponse:
        captured_requests.append(request)
        return TokenResponse()

    monkeypatch.setattr("app.services.google_calendar_service.urlopen", fake_urlopen)

    tokens = GoogleCalendarService().exchange_code_for_tokens(code="secret-auth-code", state="stale-state")

    assert tokens.access_token == "test-access-token"
    assert tokens.refresh_token == "test-refresh-token"
    assert tokens.provider_account_email == "elegantweddings12@gmail.com"
    assert len(captured_requests) == 1
    request = captured_requests[0]
    assert request.full_url == "https://oauth2.googleapis.com/token"
    form = parse_qs(request.data.decode("utf-8"))
    assert form == {
        "code": ["secret-auth-code"],
        "client_id": ["client-id"],
        "client_secret": ["client-secret"],
        "redirect_uri": ["http://localhost:8088/api/v1/integrations/calendar/google/callback"],
        "grant_type": ["authorization_code"],
    }
    assert "code_verifier" not in form


async def test_google_token_exchange_sanitizes_oauth_error(
    calendar_settings,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    monkeypatch.setattr("app.services.google_calendar_service.settings.google_client_secret", "client-secret")
    monkeypatch.setattr(
        "app.services.google_calendar_service.settings.google_redirect_uri",
        "http://localhost:8088/api/v1/integrations/calendar/google/callback",
    )
    caplog.set_level(logging.ERROR, logger="app.services.google_calendar_service")
    captured_requests: list[object] = []

    def fake_urlopen(request: object, timeout: int) -> object:
        captured_requests.append(request)
        payload = b'{"error":"invalid_grant","error_description":"Missing code verifier."}'
        raise HTTPError(
            "https://oauth2.googleapis.com/token",
            400,
            "Bad Request",
            hdrs=None,
            fp=io.BytesIO(payload),
        )

    monkeypatch.setattr("app.services.google_calendar_service.urlopen", fake_urlopen)

    with pytest.raises(GoogleCalendarOAuthError) as exc_info:
        GoogleCalendarService().exchange_code_for_tokens(code="secret-auth-code", state="stale-state")

    error = str(exc_info.value)
    assert len(captured_requests) == 1
    assert "status=400" in error
    assert "error=invalid_grant" in error
    assert "description=Missing code verifier." in error
    assert error in caplog.text
    assert "secret-auth-code" not in caplog.text
    assert "stale-state" not in caplog.text
    assert "client-secret" not in caplog.text


async def test_staff_cannot_start_connect_flow(
    client: AsyncClient,
    db_session: AsyncSession,
    demo_tenants: dict[str, Tenant],
    calendar_settings,
    fake_google: FakeGoogleCalendarService,
):
    token = await create_staff_token(db_session, demo_tenants["elegant-weddings"])

    response = await client.get(
        "/api/v1/integrations/calendar/google/connect",
        headers=auth_headers(token),
    )

    assert response.status_code == 403


async def test_callback_stores_encrypted_tokens(
    client: AsyncClient,
    db_session: AsyncSession,
    calendar_settings,
    fake_google: FakeGoogleCalendarService,
):
    token = await login(client)

    await connect_calendar(client, token)

    connection = (await db_session.execute(select(CalendarConnection))).scalar_one()
    assert connection.provider_account_email == "elegantweddings12@gmail.com"
    assert connection.access_token_encrypted != "test-access-token"
    assert connection.refresh_token_encrypted != "test-refresh-token"
    assert decrypt_calendar_token(connection.access_token_encrypted) == "test-access-token"
    assert decrypt_calendar_token(connection.refresh_token_encrypted) == "test-refresh-token"


async def test_callback_with_manual_google_token_response_creates_connection(
    client: AsyncClient,
    db_session: AsyncSession,
    calendar_settings,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr("app.services.google_calendar_service.settings.google_client_id", "client-id")
    monkeypatch.setattr("app.services.google_calendar_service.settings.google_client_secret", "client-secret")
    monkeypatch.setattr(
        "app.services.google_calendar_service.settings.google_redirect_uri",
        "http://localhost:8088/api/v1/integrations/calendar/google/callback",
    )
    monkeypatch.setattr(
        "app.services.google_calendar_service.settings.google_calendar_scopes",
        "openid email profile https://www.googleapis.com/auth/calendar.events",
    )
    app.dependency_overrides[get_google_calendar_service] = lambda: GoogleCalendarService()
    id_token = jwt.encode(
        {"email": "elegantweddings12@gmail.com"},
        "not-used-for-verification",
        algorithm="HS256",
    )
    captured_requests: list[object] = []

    class TokenResponse:
        status = 200

        def __enter__(self) -> "TokenResponse":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return (
                '{"access_token":"test-access-token","refresh_token":"test-refresh-token",'
                '"expires_in":3600,"scope":"openid email profile '
                'https://www.googleapis.com/auth/calendar.events","token_type":"Bearer",'
                f'"id_token":"{id_token}"'
                "}"
            ).encode("utf-8")

    def fake_urlopen(request: object, timeout: int) -> TokenResponse:
        captured_requests.append(request)
        return TokenResponse()

    monkeypatch.setattr("app.services.google_calendar_service.urlopen", fake_urlopen)
    token = await login(client)

    connect_response = await client.get(
        "/api/v1/integrations/calendar/google/connect",
        headers=auth_headers(token),
    )
    assert connect_response.status_code == 200
    connect_url = connect_response.json()["authorization_url"]
    query = parse_qs(urlparse(connect_url).query)
    assert "code_challenge" not in query
    assert "code_challenge_method" not in query

    callback_response = await client.get(
        "/api/v1/integrations/calendar/google/callback",
        params={"code": "auth-code", "state": query["state"][0]},
        follow_redirects=False,
    )

    assert callback_response.status_code == 307
    assert callback_response.headers["location"].endswith("/settings?calendar=connected")
    connection = (await db_session.execute(select(CalendarConnection))).scalar_one()
    assert connection.provider_account_email == "elegantweddings12@gmail.com"
    assert decrypt_calendar_token(connection.access_token_encrypted) == "test-access-token"
    assert decrypt_calendar_token(connection.refresh_token_encrypted) == "test-refresh-token"
    assert len(captured_requests) == 1
    form = parse_qs(captured_requests[0].data.decode("utf-8"))
    assert form["code"] == ["auth-code"]
    assert form["client_id"] == ["client-id"]
    assert form["client_secret"] == ["client-secret"]
    assert form["redirect_uri"] == [
        "http://localhost:8088/api/v1/integrations/calendar/google/callback"
    ]
    assert form["grant_type"] == ["authorization_code"]
    assert "code_verifier" not in form


async def test_callback_missing_refresh_token_logs_and_audits_failure(
    client: AsyncClient,
    db_session: AsyncSession,
    calendar_settings,
    caplog: pytest.LogCaptureFixture,
):
    fake = MissingRefreshTokenGoogleCalendarService()
    app.dependency_overrides[get_google_calendar_service] = lambda: fake
    caplog.set_level(logging.ERROR, logger="app.api.v1.calendar")
    token = await login(client)

    connect_response = await client.get(
        "/api/v1/integrations/calendar/google/connect",
        headers=auth_headers(token),
    )
    assert connect_response.status_code == 200
    state = parse_qs(urlparse(connect_response.json()["authorization_url"]).query)["state"][0]

    callback_response = await client.get(
        "/api/v1/integrations/calendar/google/callback",
        params={"code": "auth-code", "state": state},
        follow_redirects=False,
    )

    assert callback_response.status_code == 307
    assert callback_response.headers["location"].endswith("/settings?calendar=error")
    assert (await db_session.execute(select(CalendarConnection))).scalar_one_or_none() is None
    audit_log = (
        await db_session.execute(
            select(AuditLog).where(
                AuditLog.event_type == AUDIT_EVENT_CALENDAR_CONNECTION_FAILED
            )
        )
    ).scalar_one()
    assert audit_log.details["provider"] == "google"
    assert (
        audit_log.details["error"]
        == "Google did not return a refresh token. Remove app access from Google Account and reconnect."
    )
    assert "Google Calendar OAuth callback failed" in caplog.text
    assert "Remove app access from Google Account and reconnect" in caplog.text
    assert "auth-code" not in caplog.text


async def test_create_event_requires_active_connection(client: AsyncClient):
    token = await login(client)

    response = await client.post(
        "/api/v1/calendar/events",
        headers=auth_headers(token),
        json={
            "title": "Client meeting",
            "start_time": "2026-06-18T17:00:00+03:00",
            "end_time": "2026-06-18T17:45:00+03:00",
            "timezone": "Asia/Beirut",
        },
    )

    assert response.status_code == 409


async def test_availability_check_returns_free_when_no_events_overlap(
    client: AsyncClient,
    db_session: AsyncSession,
    calendar_settings,
    fake_google: FakeGoogleCalendarService,
):
    token = await login(client)
    await connect_calendar(client, token)

    response = await client.post(
        "/api/v1/calendar/availability/check",
        headers=auth_headers(token),
        json={
            "start_time": "2026-06-19T15:20:00+03:00",
            "end_time": "2026-06-19T16:05:00+03:00",
            "timezone": "Asia/Beirut",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["available"] is True
    assert data["reason"] == "free"
    assert data["conflicting_events_count"] == 0
    assert data["alternatives"] == []
    audit_log = (
        await db_session.execute(
            select(AuditLog).where(AuditLog.event_type == AUDIT_EVENT_CALENDAR_AVAILABILITY_CHECKED)
        )
    ).scalars().first()
    assert audit_log is not None
    assert audit_log.details["available"] is True
    assert audit_log.details["conflicts_count"] == 0


async def test_availability_check_returns_busy_when_event_overlaps(
    client: AsyncClient,
    calendar_settings,
    fake_google: FakeGoogleCalendarService,
):
    token = await login(client)
    await connect_calendar(client, token)
    fake_google.busy_events = [
        GoogleCalendarBusyEvent(
            start_time=datetime.fromisoformat("2026-06-19T15:00:00+03:00"),
            end_time=datetime.fromisoformat("2026-06-19T16:00:00+03:00"),
        ),
        GoogleCalendarBusyEvent(
            start_time=datetime.fromisoformat("2026-06-19T16:30:00+03:00"),
            end_time=datetime.fromisoformat("2026-06-19T17:15:00+03:00"),
        ),
    ]

    response = await client.post(
        "/api/v1/calendar/availability/check",
        headers=auth_headers(token),
        json={
            "start_time": "2026-06-19T15:20:00+03:00",
            "end_time": "2026-06-19T16:05:00+03:00",
            "timezone": "Asia/Beirut",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["available"] is False
    assert data["reason"] == "busy"
    assert data["conflicting_events_count"] == 1
    assert data["alternatives"][0]["start_time"] == "2026-06-19T17:30:00+03:00"


async def test_availability_check_without_connection_returns_unknown(client: AsyncClient):
    token = await login(client)

    response = await client.post(
        "/api/v1/calendar/availability/check",
        headers=auth_headers(token),
        json={
            "start_time": "2026-06-19T15:20:00+03:00",
            "end_time": "2026-06-19T16:05:00+03:00",
            "timezone": "Asia/Beirut",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["available"] is None
    assert data["reason"] == "calendar_not_connected"


async def test_availability_check_uses_only_authenticated_tenant_connection(
    client: AsyncClient,
    calendar_settings,
    fake_google: FakeGoogleCalendarService,
):
    elegant_token = await login(client)
    royal_token = await login(
        client,
        email="admin@royal-events.demo",
        password="demo-password-2",
        tenant_slug="royal-events-agency",
    )
    await connect_calendar(client, elegant_token)

    response = await client.post(
        "/api/v1/calendar/availability/check",
        headers=auth_headers(royal_token),
        json={
            "tenant_id": "00000000-0000-0000-0000-000000000000",
            "start_time": "2026-06-19T15:20:00+03:00",
            "end_time": "2026-06-19T16:05:00+03:00",
            "timezone": "Asia/Beirut",
        },
    )

    assert response.status_code == 200
    assert response.json()["reason"] == "calendar_not_connected"


async def test_staff_can_create_event_after_tenant_connection_exists(
    client: AsyncClient,
    db_session: AsyncSession,
    demo_tenants: dict[str, Tenant],
    calendar_settings,
    fake_google: FakeGoogleCalendarService,
):
    manager_token = await login(client)
    await connect_calendar(client, manager_token)
    staff_token = await create_staff_token(db_session, demo_tenants["elegant-weddings"])
    conversation = await create_conversation(client, staff_token)
    message = await create_message(client, staff_token, conversation["id"], "Can we meet tomorrow?")

    response = await client.post(
        "/api/v1/calendar/events",
        headers=auth_headers(staff_token),
        json={
            "title": "Client meeting",
            "description": "Created from EventSense",
            "start_time": "2026-06-18T17:00:00+03:00",
            "end_time": "2026-06-18T17:45:00+03:00",
            "timezone": "Asia/Beirut",
            "related_conversation_id": conversation["id"],
            "related_message_id": message["id"],
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["provider_event_id"] == "google-event-123"
    assert data["provider_event_link"] == "https://calendar.google.test/event?eid=123"
    assert data["related_message_id"] == message["id"]
    assert "access_token" not in data
    assert "refresh_token" not in data


async def test_create_event_rejects_cross_tenant_related_message(
    client: AsyncClient,
    calendar_settings,
    fake_google: FakeGoogleCalendarService,
):
    elegant_token = await login(client)
    royal_token = await login(
        client,
        email="admin@royal-events.demo",
        password="demo-password-2",
        tenant_slug="royal-events-agency",
    )
    await connect_calendar(client, elegant_token)
    royal_conversation = await create_conversation(client, royal_token, "Royal Calendar Client")
    royal_message = await create_message(client, royal_token, royal_conversation["id"], "Royal message")

    response = await client.post(
        "/api/v1/calendar/events",
        headers=auth_headers(elegant_token),
        json={
            "title": "Cross tenant event",
            "start_time": "2026-06-18T17:00:00+03:00",
            "end_time": "2026-06-18T17:45:00+03:00",
            "timezone": "Asia/Beirut",
            "related_message_id": royal_message["id"],
        },
    )

    assert response.status_code == 403


async def test_calendar_event_local_row_and_audit_logs_are_written(
    client: AsyncClient,
    db_session: AsyncSession,
    calendar_settings,
    fake_google: FakeGoogleCalendarService,
):
    token = await login(client)
    await connect_calendar(client, token)

    response = await client.post(
        "/api/v1/calendar/events",
        headers=auth_headers(token),
        json={
            "title": "Planning call",
            "start_time": "2026-06-18T17:00:00+03:00",
            "end_time": "2026-06-18T17:45:00+03:00",
            "timezone": "Asia/Beirut",
        },
    )

    assert response.status_code == 201
    event = (await db_session.execute(select(CalendarEvent))).scalar_one()
    assert event.provider_event_id == "google-event-123"
    audit_events = (
        await db_session.execute(
            select(AuditLog.event_type).where(
                AuditLog.event_type.in_(
                    [AUDIT_EVENT_CALENDAR_CONNECTED, AUDIT_EVENT_CALENDAR_EVENT_CREATED]
                )
            )
        )
    ).scalars().all()
    assert AUDIT_EVENT_CALENDAR_CONNECTED in audit_events
    assert AUDIT_EVENT_CALENDAR_EVENT_CREATED in audit_events
