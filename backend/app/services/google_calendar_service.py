from __future__ import annotations

import logging
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from jose import JWTError, jwt

from app.core.calendar_crypto import decrypt_calendar_token, encrypt_calendar_token
from app.core.config import settings
from app.models.calendar import CalendarConnection


logger = logging.getLogger(__name__)


GOOGLE_OAUTH_AUTHORIZATION_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_OAUTH_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
GOOGLE_OAUTH_ACCESS_TYPE = "offline"
GOOGLE_OAUTH_INCLUDE_GRANTED_SCOPES = "true"
GOOGLE_OAUTH_PROMPT = "consent"
GOOGLE_OAUTH_TOKEN_TIMEOUT_SECONDS = 10
MISSING_GOOGLE_REFRESH_TOKEN_ERROR = (
    "Google did not return a refresh token. Remove app access from Google Account and reconnect."
)


@dataclass(frozen=True)
class GoogleTokenBundle:
    access_token: str
    refresh_token: str
    expires_at: datetime | None
    scopes: str
    provider_account_email: str
    calendar_id: str = "primary"


@dataclass(frozen=True)
class GoogleEventResult:
    provider_event_id: str
    provider_event_link: str | None


@dataclass(frozen=True)
class GoogleCalendarBusyEvent:
    start_time: datetime
    end_time: datetime


class GoogleCalendarOAuthError(RuntimeError):
    """Sanitized Google OAuth error safe for logs and audit details."""


class GoogleCalendarService:
    def scopes(self) -> list[str]:
        return [
            scope.strip()
            for scope in settings.google_calendar_scopes.replace(",", " ").split()
            if scope.strip()
        ]

    def build_authorization_url(self, *, state: str) -> str:
        self._log_oauth_parameters("Google Calendar OAuth authorization URL parameters")
        query = urlencode(
            {
                "client_id": settings.google_client_id,
                "redirect_uri": settings.google_redirect_uri,
                "response_type": "code",
                "scope": settings.google_calendar_scopes,
                "access_type": GOOGLE_OAUTH_ACCESS_TYPE,
                "prompt": GOOGLE_OAUTH_PROMPT,
                "include_granted_scopes": GOOGLE_OAUTH_INCLUDE_GRANTED_SCOPES,
                "state": state,
            }
        )
        return f"{GOOGLE_OAUTH_AUTHORIZATION_URL}?{query}"

    def exchange_code_for_tokens(self, *, code: str, state: str | None = None) -> GoogleTokenBundle:
        self._log_oauth_parameters("Google Calendar OAuth token exchange parameters")
        token_response = self._post_token_request(
            {
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": settings.google_redirect_uri,
                "grant_type": "authorization_code",
            }
        )
        refresh_token = _string_value(token_response, "refresh_token")
        if not refresh_token:
            raise RuntimeError(MISSING_GOOGLE_REFRESH_TOKEN_ERROR)

        access_token = _string_value(token_response, "access_token")
        if not access_token:
            raise GoogleCalendarOAuthError(
                "Google Calendar OAuth token exchange failed. access_token missing"
            )

        provider_email = self._provider_account_email_from_token_response(token_response) or "unknown-google-account"
        expires_in = _int_value(token_response, "expires_in")
        return GoogleTokenBundle(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=utc_now() + timedelta(seconds=expires_in) if expires_in is not None else None,
            scopes=_string_value(token_response, "scope") or " ".join(self.scopes()),
            provider_account_email=provider_email,
        )

    def encrypt_access_token(self, token: str) -> str:
        return encrypt_calendar_token(token)

    def encrypt_refresh_token(self, token: str) -> str:
        return encrypt_calendar_token(token)

    def create_event(
        self,
        *,
        connection: CalendarConnection,
        title: str,
        description: str | None,
        start_time: datetime,
        end_time: datetime,
        timezone_name: str,
    ) -> GoogleEventResult:
        credentials = self._credentials_from_connection(connection)
        credentials = self._refresh_if_needed(credentials, connection)
        service = self._calendar_service(credentials)
        payload = {
            "summary": title,
            "description": description or "",
            "start": {"dateTime": start_time.isoformat(), "timeZone": timezone_name},
            "end": {"dateTime": end_time.isoformat(), "timeZone": timezone_name},
        }
        created = (
            service.events()
            .insert(calendarId=connection.calendar_id, body=payload)
            .execute()
        )
        return GoogleEventResult(
            provider_event_id=created["id"],
            provider_event_link=created.get("htmlLink"),
        )

    def delete_event(self, *, connection: CalendarConnection, provider_event_id: str) -> None:
        credentials = self._credentials_from_connection(connection)
        credentials = self._refresh_if_needed(credentials, connection)
        service = self._calendar_service(credentials)
        service.events().delete(
            calendarId=connection.calendar_id,
            eventId=provider_event_id,
        ).execute()

    def list_events_between(
        self,
        *,
        connection: CalendarConnection,
        start_time: datetime,
        end_time: datetime,
        timezone_name: str,
    ) -> list[GoogleCalendarBusyEvent]:
        credentials = self._credentials_from_connection(connection)
        credentials = self._refresh_if_needed(credentials, connection)
        service = self._calendar_service(credentials)
        response = (
            service.events()
            .list(
                calendarId=connection.calendar_id,
                timeMin=start_time.isoformat(),
                timeMax=end_time.isoformat(),
                timeZone=timezone_name,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        return [
            event
            for event in (
                _busy_event_from_google_item(item, timezone_name)
                for item in response.get("items", [])
                if isinstance(item, dict)
            )
            if event is not None and _events_overlap(event.start_time, event.end_time, start_time, end_time)
        ]

    def _log_oauth_parameters(self, message: str) -> None:
        logger.debug(
            "%s: redirect_uri=%s scopes=%s access_type=%s prompt=%s include_granted_scopes=%s",
            message,
            settings.google_redirect_uri,
            self.scopes(),
            GOOGLE_OAUTH_ACCESS_TYPE,
            GOOGLE_OAUTH_PROMPT,
            GOOGLE_OAUTH_INCLUDE_GRANTED_SCOPES,
        )

    def _post_token_request(self, form: dict[str, str]) -> dict[str, object]:
        body = urlencode(form).encode("utf-8")
        request = Request(
            GOOGLE_OAUTH_TOKEN_URL,
            data=body,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=GOOGLE_OAUTH_TOKEN_TIMEOUT_SECONDS) as response:
                status_code = response.status
                payload = _json_response_payload(response.read())
        except HTTPError as exc:
            payload = _json_response_payload(exc.read())
            sanitized_error = _sanitize_oauth_token_response_error(exc.code, payload)
            logger.error(sanitized_error)
            raise GoogleCalendarOAuthError(sanitized_error) from None
        except URLError as exc:
            sanitized_error = (
                "Google Calendar OAuth token exchange failed. "
                f"class={exc.__class__.__name__} description={_safe_oauth_detail(str(exc.reason))}"
            )
            logger.error(sanitized_error)
            raise GoogleCalendarOAuthError(sanitized_error) from None

        if status_code != 200:
            sanitized_error = _sanitize_oauth_token_response_error(status_code, payload)
            logger.error(sanitized_error)
            raise GoogleCalendarOAuthError(sanitized_error)
        return payload

    def _credentials_from_connection(self, connection: CalendarConnection):
        from google.oauth2.credentials import Credentials

        return Credentials(
            token=decrypt_calendar_token(connection.access_token_encrypted),
            refresh_token=decrypt_calendar_token(connection.refresh_token_encrypted),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            scopes=connection.scopes.split(),
        )

    def _refresh_if_needed(self, credentials: Any, connection: CalendarConnection):
        if credentials.valid:
            return credentials
        if not credentials.expired or not credentials.refresh_token:
            return credentials

        from google.auth.transport.requests import Request

        credentials.refresh(Request())
        connection.access_token_encrypted = encrypt_calendar_token(credentials.token)
        connection.token_expires_at = credentials.expiry
        return credentials

    def _calendar_service(self, credentials: Any):
        from googleapiclient.discovery import build

        return build("calendar", "v3", credentials=credentials, cache_discovery=False)

    def _provider_account_email_from_token_response(self, token_response: dict[str, object]) -> str | None:
        id_token = _string_value(token_response, "id_token")
        if id_token:
            try:
                claims = jwt.get_unverified_claims(id_token)
                email = claims.get("email")
                if isinstance(email, str) and email:
                    return email
            except JWTError:
                pass

        access_token = _string_value(token_response, "access_token")
        if not access_token:
            return None
        return self._provider_account_email_from_userinfo(access_token)

    def _provider_account_email_from_userinfo(self, access_token: str) -> str | None:
        request = Request(
            GOOGLE_OAUTH_USERINFO_URL,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {access_token}",
            },
            method="GET",
        )
        try:
            with urlopen(request, timeout=GOOGLE_OAUTH_TOKEN_TIMEOUT_SECONDS) as response:
                payload = _json_response_payload(response.read())
        except Exception:
            return None
        email = payload.get("email")
        return email if isinstance(email, str) and email else None

    def _provider_account_email(
        self,
        credentials: Any,
        *,
        token_response: dict[str, Any] | None = None,
    ) -> str | None:
        id_token = getattr(credentials, "id_token", None)
        if not id_token and token_response:
            token_id_token = token_response.get("id_token")
            if isinstance(token_id_token, str):
                id_token = token_id_token
        if id_token:
            try:
                claims = jwt.get_unverified_claims(id_token)
                email = claims.get("email")
                if isinstance(email, str) and email:
                    return email
            except JWTError:
                pass

        try:
            service = self._calendar_service(credentials)
            primary = service.calendars().get(calendarId="primary").execute()
            for key in ("id", "summary"):
                value = primary.get(key)
                if isinstance(value, str) and "@" in value:
                    return value
        except Exception:
            return None
        return None


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _sanitize_oauth_token_response_error(status_code: int, payload: dict[str, object]) -> str:
    parts = [
        "Google Calendar OAuth token exchange failed.",
        f"status={status_code}",
    ]
    oauth_error = _oauth_response_field(payload, "error")
    if oauth_error:
        parts.append(f"error={oauth_error}")
    oauth_description = _oauth_response_field(payload, "error_description")
    if oauth_description:
        parts.append(f"description={oauth_description}")
    return " ".join(parts)


def _oauth_response_field(payload: dict[str, object], key: str) -> str | None:
    value = payload.get(key)
    if isinstance(value, str) and value:
        return _safe_oauth_detail(value)
    return None


def _json_response_payload(body: bytes) -> dict[str, object]:
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _string_value(payload: dict[str, object], key: str) -> str | None:
    value = payload.get(key)
    return value if isinstance(value, str) and value else None


def _int_value(payload: dict[str, object], key: str) -> int | None:
    value = payload.get(key)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _busy_event_from_google_item(
    item: dict[str, object],
    timezone_name: str,
) -> GoogleCalendarBusyEvent | None:
    status = item.get("status")
    if status == "cancelled":
        return None
    transparency = item.get("transparency")
    if transparency == "transparent":
        return None

    start = _event_endpoint_datetime(item.get("start"), timezone_name)
    end = _event_endpoint_datetime(item.get("end"), timezone_name)
    if start is None or end is None or end <= start:
        return None
    return GoogleCalendarBusyEvent(start_time=start, end_time=end)


def _event_endpoint_datetime(value: object, timezone_name: str) -> datetime | None:
    if not isinstance(value, dict):
        return None
    date_time = _string_value(value, "dateTime")
    if date_time:
        return _parse_google_datetime(date_time)

    date_value = _string_value(value, "date")
    if not date_value:
        return None
    from zoneinfo import ZoneInfo

    parsed_date = datetime.fromisoformat(date_value)
    return parsed_date.replace(tzinfo=ZoneInfo(timezone_name))


def _parse_google_datetime(value: str) -> datetime | None:
    try:
        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _events_overlap(
    event_start: datetime,
    event_end: datetime,
    requested_start: datetime,
    requested_end: datetime,
) -> bool:
    return event_start < requested_end and event_end > requested_start


def _safe_oauth_detail(value: str) -> str:
    forbidden_markers = (
        "access_token",
        "refresh_token",
        "id_token",
        "client_secret",
    )
    if any(marker in value.lower() for marker in forbidden_markers):
        return "[redacted]"
    return value[:500]
