import enum
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.core.database import Base, TimestampMixin


class SuggestedReplyStatus(str, enum.Enum):
    draft = "draft"
    approved = "approved"
    edited = "edited"
    rejected = "rejected"


class SuggestedReply(TimestampMixin, Base):
    __tablename__ = "suggested_replies"
    __table_args__ = (
        Index("ix_suggested_replies_tenant_id", "tenant_id"),
        Index(
            "ix_suggested_replies_tenant_id_conversation_id",
            "tenant_id",
            "conversation_id",
        ),
        Index("ix_suggested_replies_tenant_id_message_id", "tenant_id", "message_id"),
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
    suggested_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[SuggestedReplyStatus] = mapped_column(
        Enum(SuggestedReplyStatus, name="suggested_reply_status"),
        nullable=False,
        default=SuggestedReplyStatus.draft,
    )
    source_document_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    rag_sources: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False, default=list)
    answer_supported: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    refusal_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    generation_method: Mapped[str] = mapped_column(String(40), nullable=False, default="template_v1")
    # Set when the reply was delivered to the client automatically (e.g. Telegram
    # auto-reply) rather than approved by a human. When populated, the dashboard
    # shows the reply as already sent and hides the approve/dismiss actions.
    auto_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_channel: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    conversation = relationship("Conversation")
    message = relationship("Message", foreign_keys=[message_id])
