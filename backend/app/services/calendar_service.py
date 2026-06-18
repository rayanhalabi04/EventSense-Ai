from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from jose import ExpiredSignatureError, JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.tenant_context import TenantContext
from app.models.calendar import (
    CalendarConnection,
    CalendarConnectionType,
    CalendarEvent,
    CalendarEventSyncStatus,
    CalendarProvider,
)
from app.models.user import UserRole
from app.repositories.calendar_connection_repository import CalendarConnectionRepository
from app.repositories.calendar_event_repository import CalendarEventRepository
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.escalation_repository import EscalationRepository
from app.repositories.message_repository import MessageRepository
from app.repositories.task_repository import TaskRepository
from app.schemas.calendar import (
    CalendarAvailabilityResponse,
    CalendarAvailabilitySlot,
    CalendarEventCreate,
    CalendarStatusResponse,
)
from app.services.audit_log_service import AuditLogService
from app.services.google_calendar_service import GoogleCalendarService


AUDIT_EVENT_CALENDAR_CONNECTED = "calendar.connected"
AUDIT_EVENT_CALENDAR_CONNECTION_FAILED = "calendar.connection_failed"
AUDIT_EVENT_CALENDAR_DISCONNECTED = "calendar.disconnected"
AUDIT_EVENT_CALENDAR_EVENT_CREATED = "calendar.event_created"
AUDIT_EVENT_CALENDAR_EVENT_CREATE_FAILED = "calendar.event_create_failed"
AUDIT_EVENT_CALENDAR_EVENT_DELETED = "calendar.event_deleted"
AUDIT_EVENT_CALENDAR_AVAILABILITY_CHECKED = "calendar.availability_checked"
AUDIT_EVENT_CALENDAR_AVAILABILITY_CHECK_FAILED = "calendar.availability_check_failed"
DEFAULT_CALENDAR_TIMEZONE = "Asia/Beirut"
DEFAULT_MEETING_DURATION_MINUTES = 45


class CalendarService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        google_calendar_service: GoogleCalendarService | None = None,
    ) -> None:
        self.session = session
        self.connections = CalendarConnectionRepository(session)
        self.events = CalendarEventRepository(session)
        self.conversations = ConversationRepository(session)
        self.messages = MessageRepository(session)
        self.tasks = TaskRepository(session)
        self.escalations = EscalationRepository(session)
        self.google = google_calendar_service or GoogleCalendarService()

    async def status(self, ctx: TenantContext) -> CalendarStatusResponse:
        connection = await self.connections.get_active_for_tenant(ctx.tenant_id)
        if connection is None:
            return CalendarStatusResponse(connected=False)
        return CalendarStatusResponse(
            connected=True,
            provider=connection.provider,
            provider_account_email=connection.provider_account_email,
            calendar_id=connection.calendar_id,
            connection_type=connection.connection_type,
        )

    def build_connect_url(self, ctx: TenantContext) -> str:
        self._require_enabled()
        self._require_manager(ctx)
        state = self._encode_state(ctx)
        return self.google.build_authorization_url(state=state)

    async def handle_google_callback(self, *, code: str, state: str) -> None:
        self._require_enabled()
        tenant_id, user_id = self._decode_state(state)
        tokens = self.google.exchange_code_for_tokens(code=code, state=state)

        await self.connections.deactivate_active_for_tenant(tenant_id)
        connection = CalendarConnection(
            tenant_id=tenant_id,
            connected_by_user_id=user_id,
            provider=CalendarProvider.google,
            provider_account_email=tokens.provider_account_email,
            calendar_id=tokens.calendar_id,
            access_token_encrypted=self.google.encrypt_access_token(tokens.access_token),
            refresh_token_encrypted=self.google.encrypt_refresh_token(tokens.refresh_token),
            token_expires_at=tokens.expires_at,
            scopes=tokens.scopes,
            connection_type=CalendarConnectionType.tenant_shared,
            is_active=True,
        )
        await self.connections.add(connection)
        AuditLogService.record(
            self.session,
            tenant_id=tenant_id,
            actor_user_id=user_id,
            event_type=AUDIT_EVENT_CALENDAR_CONNECTED,
            resource_type="calendar_connection",
            resource_id=connection.id,
            details={
                "provider": connection.provider,
                "provider_account_email": connection.provider_account_email,
                "calendar_id": connection.calendar_id,
                "connection_type": connection.connection_type,
            },
        )
        await self.session.commit()

    async def record_google_connection_failure(self, *, state: str | None, error: str) -> bool:
        if not state:
            return False
        try:
            tenant_id, user_id = self._decode_state(state)
        except HTTPException:
            return False

        AuditLogService.record(
            self.session,
            tenant_id=tenant_id,
            actor_user_id=user_id,
            event_type=AUDIT_EVENT_CALENDAR_CONNECTION_FAILED,
            resource_type="calendar_connection",
            details={
                "provider": "google",
                "error": error,
                "connection_type": "tenant_shared",
            },
        )
        await self.session.commit()
        return True

    async def disconnect(self, ctx: TenantContext) -> None:
        self._require_manager(ctx)
        count = await self.connections.deactivate_active_for_tenant(ctx.tenant_id)
        if count:
            AuditLogService.record(
                self.session,
                tenant_id=ctx.tenant_id,
                actor_user_id=ctx.user_id,
                event_type=AUDIT_EVENT_CALENDAR_DISCONNECTED,
                resource_type="calendar_connection",
                details={"provider": "google", "connection_type": "tenant_shared"},
            )
        await self.session.commit()

    async def create_event(self, payload: CalendarEventCreate, ctx: TenantContext) -> CalendarEvent:
        connection = await self.connections.get_active_for_tenant(ctx.tenant_id)
        if connection is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="tenant calendar is not connected",
            )

        await self._validate_related_records(payload, ctx)
        local_event = CalendarEvent(
            tenant_id=ctx.tenant_id,
            created_by_user_id=ctx.user_id,
            calendar_connection_id=connection.id,
            provider=CalendarProvider.google,
            calendar_id=connection.calendar_id,
            title=payload.title,
            description=payload.description,
            start_time=payload.start_time,
            end_time=payload.end_time,
            timezone=payload.timezone,
            related_conversation_id=payload.related_conversation_id,
            related_message_id=payload.related_message_id,
            related_task_id=payload.related_task_id,
            related_escalation_id=payload.related_escalation_id,
            sync_status=CalendarEventSyncStatus.created,
        )

        try:
            result = self.google.create_event(
                connection=connection,
                title=payload.title,
                description=payload.description,
                start_time=payload.start_time,
                end_time=payload.end_time,
                timezone_name=payload.timezone,
            )
            local_event.provider_event_id = result.provider_event_id
            local_event.provider_event_link = result.provider_event_link
            await self.events.add(local_event)
            AuditLogService.record(
                self.session,
                tenant_id=ctx.tenant_id,
                actor_user_id=ctx.user_id,
                event_type=AUDIT_EVENT_CALENDAR_EVENT_CREATED,
                resource_type="calendar_event",
                resource_id=local_event.id,
                details=_event_audit_details(local_event),
            )
            await self.session.commit()
            await self.session.refresh(local_event)
            return local_event
        except Exception as exc:
            local_event.sync_status = CalendarEventSyncStatus.failed
            local_event.error_message = str(exc)
            await self.events.add(local_event)
            AuditLogService.record(
                self.session,
                tenant_id=ctx.tenant_id,
                actor_user_id=ctx.user_id,
                event_type=AUDIT_EVENT_CALENDAR_EVENT_CREATE_FAILED,
                resource_type="calendar_event",
                resource_id=local_event.id,
                details={**_event_audit_details(local_event), "error": str(exc)},
            )
            await self.session.commit()
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="failed to create Google Calendar event",
            ) from exc

    async def list_events(self, ctx: TenantContext) -> list[CalendarEvent]:
        return await self.events.list_for_tenant(ctx.tenant_id)

    async def check_tenant_availability(
        self,
        *,
        start_time: datetime,
        end_time: datetime,
        timezone_name: str = DEFAULT_CALENDAR_TIMEZONE,
        ctx: TenantContext | None = None,
        tenant_id: UUID | None = None,
        actor_user_id: UUID | None = None,
        commit: bool = True,
    ) -> CalendarAvailabilityResponse:
        resolved_tenant_id = ctx.tenant_id if ctx is not None else tenant_id
        resolved_actor_user_id = ctx.user_id if ctx is not None else actor_user_id
        if resolved_tenant_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="tenant context is required",
            )

        connection = await self.connections.get_active_for_tenant(resolved_tenant_id)
        requested_start = _ensure_timezone(start_time, timezone_name)
        requested_end = _ensure_timezone(end_time, timezone_name)
        if requested_end <= requested_start:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="end_time must be after start_time",
            )

        if connection is None:
            response = CalendarAvailabilityResponse(
                available=None,
                reason="calendar_not_connected",
                conflicting_events_count=0,
                alternatives=[],
                requested_start_time=requested_start,
                requested_end_time=requested_end,
                timezone=timezone_name,
            )
            self._record_availability_checked(
                tenant_id=resolved_tenant_id,
                actor_user_id=resolved_actor_user_id,
                response=response,
            )
            if commit:
                await self.session.commit()
            return response

        try:
            conflicts = self.google.list_events_between(
                connection=connection,
                start_time=requested_start,
                end_time=requested_end,
                timezone_name=timezone_name,
            )
            available = len(conflicts) == 0
            alternatives: list[CalendarAvailabilitySlot] = []
            if not available:
                alternatives = self._find_same_day_alternatives(
                    connection=connection,
                    requested_start=requested_start,
                    requested_end=requested_end,
                    timezone_name=timezone_name,
                )
            response = CalendarAvailabilityResponse(
                available=available,
                reason="free" if available else "busy",
                conflicting_events_count=len(conflicts),
                alternatives=alternatives,
                requested_start_time=requested_start,
                requested_end_time=requested_end,
                timezone=timezone_name,
            )
            self._record_availability_checked(
                tenant_id=resolved_tenant_id,
                actor_user_id=resolved_actor_user_id,
                response=response,
            )
            if commit:
                await self.session.commit()
            return response
        except HTTPException:
            raise
        except Exception as exc:
            AuditLogService.record(
                self.session,
                tenant_id=resolved_tenant_id,
                actor_user_id=resolved_actor_user_id,
                event_type=AUDIT_EVENT_CALENDAR_AVAILABILITY_CHECK_FAILED,
                resource_type="calendar_connection",
                resource_id=connection.id,
                details={
                    "requested_start_time": requested_start,
                    "requested_end_time": requested_end,
                    "available": False,
                    "conflicts_count": 0,
                    "reason": "google_calendar_error",
                    "error": exc.__class__.__name__,
                },
            )
            if commit:
                await self.session.commit()
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="failed to check Google Calendar availability",
            ) from exc

    async def delete_event(self, event_id: UUID, ctx: TenantContext) -> None:
        event = await self.events.get_for_tenant(ctx.tenant_id, event_id)
        if event is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="calendar event not found")
        connection = await self.connections.get_active_for_tenant(ctx.tenant_id)
        if connection is not None and event.provider_event_id:
            self.google.delete_event(connection=connection, provider_event_id=event.provider_event_id)
        event.sync_status = CalendarEventSyncStatus.deleted
        AuditLogService.record(
            self.session,
            tenant_id=ctx.tenant_id,
            actor_user_id=ctx.user_id,
            event_type=AUDIT_EVENT_CALENDAR_EVENT_DELETED,
            resource_type="calendar_event",
            resource_id=event.id,
            details=_event_audit_details(event),
        )
        await self.session.commit()

    async def _validate_related_records(self, payload: CalendarEventCreate, ctx: TenantContext) -> None:
        conversation_id = payload.related_conversation_id
        if conversation_id is not None:
            conversation = await self.conversations.get(conversation_id)
            if conversation is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="conversation not found")
            if conversation.tenant_id != ctx.tenant_id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")

        if payload.related_message_id is not None:
            message = await self.messages.get(payload.related_message_id)
            if message is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="message not found")
            if message.tenant_id != ctx.tenant_id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
            if conversation_id is not None and message.conversation_id != conversation_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="message does not belong to conversation",
                )

        if payload.related_task_id is not None:
            task = await self.tasks.get(payload.related_task_id)
            if task is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")
            if task.tenant_id != ctx.tenant_id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")

        if payload.related_escalation_id is not None:
            escalation = await self.escalations.get(payload.related_escalation_id)
            if escalation is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="escalation not found")
            if escalation.tenant_id != ctx.tenant_id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")

    def _require_enabled(self) -> None:
        if not settings.google_calendar_enabled:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="calendar integration disabled")
        if not settings.google_client_id or not settings.google_client_secret:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="calendar integration not configured")

    def _require_manager(self, ctx: TenantContext) -> None:
        if ctx.role != UserRole.manager:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")

    def _encode_state(self, ctx: TenantContext) -> str:
        now = datetime.now(timezone.utc)
        payload = {
            "sub": str(ctx.user_id),
            "tenant_id": str(ctx.tenant_id),
            "role": ctx.role.value,
            "purpose": "google_calendar_oauth",
            "iat": int(now.timestamp()),
            "exp": now + timedelta(minutes=15),
        }
        return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

    def _decode_state(self, state: str) -> tuple[UUID, UUID]:
        try:
            payload = jwt.decode(state, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
            if payload.get("purpose") != "google_calendar_oauth":
                raise ValueError("invalid purpose")
            return UUID(str(payload["tenant_id"])), UUID(str(payload["sub"]))
        except ExpiredSignatureError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="oauth state expired") from exc
        except (JWTError, KeyError, ValueError) as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid oauth state") from exc

    def _find_same_day_alternatives(
        self,
        *,
        connection: CalendarConnection,
        requested_start: datetime,
        requested_end: datetime,
        timezone_name: str,
    ) -> list[CalendarAvailabilitySlot]:
        duration = requested_end - requested_start
        local_start = requested_start.astimezone(ZoneInfo(timezone_name))
        local_day_end = datetime.combine(local_start.date(), time(23, 59), tzinfo=ZoneInfo(timezone_name))
        busy_events = self.google.list_events_between(
            connection=connection,
            start_time=requested_end,
            end_time=local_day_end,
            timezone_name=timezone_name,
        )
        alternatives: list[CalendarAvailabilitySlot] = []
        candidate_start = _ceil_to_next_half_hour(requested_end.astimezone(ZoneInfo(timezone_name)))
        while candidate_start + duration <= local_day_end and len(alternatives) < 2:
            candidate_end = candidate_start + duration
            if not any(
                _events_overlap(event.start_time, event.end_time, candidate_start, candidate_end)
                for event in busy_events
            ):
                alternatives.append(
                    CalendarAvailabilitySlot(
                        start_time=candidate_start,
                        end_time=candidate_end,
                    )
                )
            candidate_start += timedelta(minutes=30)
        return alternatives

    def _record_availability_checked(
        self,
        *,
        tenant_id: UUID,
        actor_user_id: UUID | None,
        response: CalendarAvailabilityResponse,
    ) -> None:
        AuditLogService.record(
            self.session,
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            event_type=AUDIT_EVENT_CALENDAR_AVAILABILITY_CHECKED,
            resource_type="calendar_connection",
            details={
                "requested_start_time": response.requested_start_time,
                "requested_end_time": response.requested_end_time,
                "available": response.available is True,
                "conflicts_count": response.conflicting_events_count,
                "reason": response.reason,
            },
        )


def _event_audit_details(event: CalendarEvent) -> dict[str, object]:
    return {
        "calendar_event_id": event.id,
        "provider": event.provider,
        "provider_event_id": event.provider_event_id,
        "calendar_id": event.calendar_id,
        "related_conversation_id": event.related_conversation_id,
        "related_message_id": event.related_message_id,
        "related_task_id": event.related_task_id,
        "related_escalation_id": event.related_escalation_id,
        "sync_status": event.sync_status,
    }


def _ensure_timezone(value: datetime, timezone_name: str) -> datetime:
    tz = ZoneInfo(timezone_name)
    if value.tzinfo is None:
        return value.replace(tzinfo=tz)
    return value.astimezone(tz)


def _ceil_to_next_half_hour(value: datetime) -> datetime:
    value = value.replace(second=0, microsecond=0)
    minutes = value.minute
    if minutes == 0 or minutes == 30:
        return value
    if minutes < 30:
        return value.replace(minute=30)
    return (value + timedelta(hours=1)).replace(minute=0)


def _events_overlap(
    event_start: datetime,
    event_end: datetime,
    requested_start: datetime,
    requested_end: datetime,
) -> bool:
    return event_start < requested_end and event_end > requested_start
