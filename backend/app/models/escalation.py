import enum
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.core.database import Base, TimestampMixin


class EscalationStatus(str, enum.Enum):
    open = "open"
    in_review = "in_review"
    resolved = "resolved"
    cancelled = "cancelled"


class Escalation(TimestampMixin, Base):
    __tablename__ = "escalations"
    __table_args__ = (
        Index("ix_escalations_tenant_id", "tenant_id"),
        Index("ix_escalations_tenant_id_status", "tenant_id", "status"),
        Index("ix_escalations_tenant_id_conversation_id", "tenant_id", "conversation_id"),
        Index(
            "ix_escalations_tenant_id_assigned_manager_user_id",
            "tenant_id",
            "assigned_manager_user_id",
        ),
        Index(
            "ix_escalations_tenant_id_source_message_id",
            "tenant_id",
            "source_message_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    conversation_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    message_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    assigned_manager_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    intent_label: Mapped[str | None] = mapped_column(String(40), nullable=True)
    risk_level: Mapped[str | None] = mapped_column(String(20), nullable=True)
    risk_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    suggested_next_step: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[EscalationStatus] = mapped_column(
        Enum(EscalationStatus, name="escalation_status"),
        nullable=False,
        default=EscalationStatus.open,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Provenance for idempotency. "agent" marks an agent-created record; NULL for
    # human/UI-created. source_message_id is a plain dedup marker (no FK).
    source_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    source_message_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)

    conversation = relationship("Conversation", back_populates="escalations")
    message = relationship("Message", foreign_keys=[message_id])
