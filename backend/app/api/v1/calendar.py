import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_async_session
from app.core.tenant_context import TenantContext, require_role
from app.models.calendar import CalendarEvent
from app.models.user import UserRole
from app.schemas.calendar import (
    CalendarAvailabilityCheckRequest,
    CalendarAvailabilityResponse,
    CalendarConnectResponse,
    CalendarEventCreate,
    CalendarEventRead,
    CalendarStatusResponse,
)
from app.services.calendar_service import CalendarService
from app.services.google_calendar_service import (
    GoogleCalendarOAuthError,
    GoogleCalendarService,
    MISSING_GOOGLE_REFRESH_TOKEN_ERROR,
)


integrations_router = APIRouter()
events_router = APIRouter()
availability_router = APIRouter()
logger = logging.getLogger(__name__)


def get_google_calendar_service() -> GoogleCalendarService:
    return GoogleCalendarService()


def _calendar_service(
    session: AsyncSession,
    google: GoogleCalendarService,
) -> CalendarService:
    return CalendarService(session, google_calendar_service=google)


@integrations_router.get("/status", response_model=CalendarStatusResponse)
async def calendar_status(
    ctx: TenantContext = Depends(require_role(UserRole.staff, UserRole.manager)),
    session: AsyncSession = Depends(get_async_session),
    google: GoogleCalendarService = Depends(get_google_calendar_service),
) -> CalendarStatusResponse:
    return await _calendar_service(session, google).status(ctx)


@integrations_router.get("/google/connect", response_model=CalendarConnectResponse)
async def google_connect(
    ctx: TenantContext = Depends(require_role(UserRole.manager)),
    session: AsyncSession = Depends(get_async_session),
    google: GoogleCalendarService = Depends(get_google_calendar_service),
) -> CalendarConnectResponse:
    authorization_url = _calendar_service(session, google).build_connect_url(ctx)
    return CalendarConnectResponse(authorization_url=authorization_url)


@integrations_router.get("/google/callback")
async def google_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    session: AsyncSession = Depends(get_async_session),
    google: GoogleCalendarService = Depends(get_google_calendar_service),
) -> RedirectResponse:
    service = _calendar_service(session, google)
    if error or not code or not state:
        await _record_google_connection_failure(
            session=session,
            service=service,
            state=state,
            error="Google Calendar OAuth callback failed.",
        )
        return RedirectResponse(f"{settings.frontend_url}/settings?calendar=error")
    try:
        await service.handle_google_callback(code=code, state=state)
    except Exception as exc:
        sanitized_error = _sanitize_google_callback_error(exc)
        _log_google_callback_exception(sanitized_error, exc)
        await _record_google_connection_failure(
            session=session,
            service=service,
            state=state,
            error=sanitized_error,
        )
        return RedirectResponse(f"{settings.frontend_url}/settings?calendar=error")
    return RedirectResponse(f"{settings.frontend_url}/settings?calendar=connected")


def _sanitize_google_callback_error(exc: Exception) -> str:
    if isinstance(exc, GoogleCalendarOAuthError):
        return str(exc)
    if str(exc) == MISSING_GOOGLE_REFRESH_TOKEN_ERROR:
        return MISSING_GOOGLE_REFRESH_TOKEN_ERROR
    return "Google Calendar OAuth callback failed."


def _log_google_callback_exception(sanitized_error: str, exc: Exception) -> None:
    try:
        raise RuntimeError(sanitized_error).with_traceback(exc.__traceback__) from None
    except RuntimeError:
        logger.exception("Google Calendar OAuth callback failed")


async def _record_google_connection_failure(
    *,
    session: AsyncSession,
    service: CalendarService,
    state: str | None,
    error: str,
) -> None:
    await session.rollback()
    try:
        await service.record_google_connection_failure(state=state, error=error)
    except Exception:
        await session.rollback()
        logger.exception("Failed to record Google Calendar OAuth failure audit log")


@integrations_router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_calendar(
    ctx: TenantContext = Depends(require_role(UserRole.manager)),
    session: AsyncSession = Depends(get_async_session),
    google: GoogleCalendarService = Depends(get_google_calendar_service),
) -> None:
    await _calendar_service(session, google).disconnect(ctx)


@events_router.post("", response_model=CalendarEventRead, status_code=status.HTTP_201_CREATED)
async def create_calendar_event(
    payload: CalendarEventCreate,
    ctx: TenantContext = Depends(require_role(UserRole.staff, UserRole.manager)),
    session: AsyncSession = Depends(get_async_session),
    google: GoogleCalendarService = Depends(get_google_calendar_service),
) -> CalendarEvent:
    return await _calendar_service(session, google).create_event(payload, ctx)


@events_router.get("", response_model=list[CalendarEventRead])
async def list_calendar_events(
    ctx: TenantContext = Depends(require_role(UserRole.staff, UserRole.manager)),
    session: AsyncSession = Depends(get_async_session),
    google: GoogleCalendarService = Depends(get_google_calendar_service),
) -> list[CalendarEvent]:
    return await _calendar_service(session, google).list_events(ctx)


@events_router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_calendar_event(
    event_id: UUID,
    ctx: TenantContext = Depends(require_role(UserRole.staff, UserRole.manager)),
    session: AsyncSession = Depends(get_async_session),
    google: GoogleCalendarService = Depends(get_google_calendar_service),
) -> None:
    await _calendar_service(session, google).delete_event(event_id, ctx)


@availability_router.post("/check", response_model=CalendarAvailabilityResponse)
async def check_calendar_availability(
    payload: CalendarAvailabilityCheckRequest,
    ctx: TenantContext = Depends(require_role(UserRole.staff, UserRole.manager)),
    session: AsyncSession = Depends(get_async_session),
    google: GoogleCalendarService = Depends(get_google_calendar_service),
) -> CalendarAvailabilityResponse:
    return await _calendar_service(session, google).check_tenant_availability(
        start_time=payload.start_time,
        end_time=payload.end_time,
        timezone_name=payload.timezone,
        ctx=ctx,
    )
