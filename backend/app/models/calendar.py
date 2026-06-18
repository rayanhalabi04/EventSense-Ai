import enum
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import expression
from sqlalchemy.types import Uuid

from app.core.database import Base, TimestampMixin


class CalendarProvider(str, enum.Enum):
    google = "google"


class CalendarConnectionType(str, enum.Enum):
    tenant_shared = "tenant_shared"


class CalendarEventSyncStatus(str, enum.Enum):
    created = "created"
    failed = "failed"
    deleted = "deleted"


class CalendarConnection(TimestampMixin, Base):
    __tablename__ = "calendar_connections"
    __table_args__ = (
        Index("ix_calendar_connections_tenant_id", "tenant_id"),
        Index(
            "uq_calendar_connections_active_google_tenant_shared",
            "tenant_id",
            "provider",
            "connection_type",
            unique=True,
            postgresql_where=expression.text("is_active = true"),
            sqlite_where=expression.text("is_active = 1"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    connected_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    provider: Mapped[CalendarProvider] = mapped_column(
        Enum(CalendarProvider, name="calendar_provider"),
        nullable=False,
        default=CalendarProvider.google,
    )
    provider_account_email: Mapped[str] = mapped_column(String(320), nullable=False)
    calendar_id: Mapped[str] = mapped_column(String(255), nullable=False, default="primary")
    access_token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scopes: Mapped[str] = mapped_column(Text, nullable=False)
    connection_type: Mapped[CalendarConnectionType] = mapped_column(
        Enum(CalendarConnectionType, name="calendar_connection_type"),
        nullable=False,
        default=CalendarConnectionType.tenant_shared,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    events = relationship("CalendarEvent", back_populates="calendar_connection")


class CalendarEvent(TimestampMixin, Base):
    __tablename__ = "calendar_events"
    __table_args__ = (
        Index("ix_calendar_events_tenant_id", "tenant_id"),
        Index("ix_calendar_events_tenant_id_start_time", "tenant_id", "start_time"),
        Index("ix_calendar_events_tenant_id_related_task_id", "tenant_id", "related_task_id"),
        Index(
            "ix_calendar_events_tenant_id_related_conversation_id",
            "tenant_id",
            "related_conversation_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    calendar_connection_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("calendar_connections.id", ondelete="SET NULL"), nullable=True
    )
    provider: Mapped[CalendarProvider] = mapped_column(
        Enum(CalendarProvider, name="calendar_provider"),
        nullable=False,
        default=CalendarProvider.google,
    )
    provider_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_event_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    calendar_id: Mapped[str] = mapped_column(String(255), nullable=False, default="primary")
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    timezone: Mapped[str] = mapped_column(String(100), nullable=False)
    related_conversation_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True
    )
    related_message_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    related_task_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
    )
    related_escalation_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("escalations.id", ondelete="SET NULL"), nullable=True
    )
    sync_status: Mapped[CalendarEventSyncStatus] = mapped_column(
        Enum(CalendarEventSyncStatus, name="calendar_event_sync_status"),
        nullable=False,
        default=CalendarEventSyncStatus.created,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    calendar_connection = relationship("CalendarConnection", back_populates="events")
