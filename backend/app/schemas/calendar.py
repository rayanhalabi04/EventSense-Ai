from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.calendar import CalendarConnectionType, CalendarEventSyncStatus, CalendarProvider


class CalendarStatusResponse(BaseModel):
    connected: bool
    provider: CalendarProvider | None = None
    provider_account_email: str | None = None
    calendar_id: str | None = None
    connection_type: CalendarConnectionType | None = None


class CalendarConnectResponse(BaseModel):
    authorization_url: str


class CalendarEventCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    start_time: datetime
    end_time: datetime
    timezone: str = Field(min_length=1, max_length=100)
    related_conversation_id: UUID | None = None
    related_message_id: UUID | None = None
    related_task_id: UUID | None = None
    related_escalation_id: UUID | None = None

    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="after")
    def validate_times(self) -> "CalendarEventCreate":
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


class CalendarEventRead(BaseModel):
    id: UUID
    tenant_id: UUID
    created_by_user_id: UUID | None
    calendar_connection_id: UUID | None
    provider: CalendarProvider
    provider_event_id: str | None
    provider_event_link: str | None
    calendar_id: str
    title: str
    description: str | None
    start_time: datetime
    end_time: datetime
    timezone: str
    related_conversation_id: UUID | None
    related_message_id: UUID | None
    related_task_id: UUID | None
    related_escalation_id: UUID | None
    sync_status: CalendarEventSyncStatus
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CalendarAvailabilitySlot(BaseModel):
    start_time: datetime
    end_time: datetime


class CalendarAvailabilityCheckRequest(BaseModel):
    start_time: datetime
    end_time: datetime
    timezone: str = Field(default="Asia/Beirut", min_length=1, max_length=100)

    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="after")
    def validate_times(self) -> "CalendarAvailabilityCheckRequest":
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


class CalendarAvailabilityResponse(BaseModel):
    available: bool | None
    reason: str
    conflicting_events_count: int = 0
    alternatives: list[CalendarAvailabilitySlot] = Field(default_factory=list)
    requested_start_time: datetime | None = None
    requested_end_time: datetime | None = None
    requested_label: str | None = None
    reason_label: str | None = None
    timezone: str = "Asia/Beirut"
