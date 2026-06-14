import enum
import json
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, Index, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.types import UserDefinedType, Uuid

from app.core.config import settings
from app.core.database import Base, TimestampMixin


class DocumentType(str, enum.Enum):
    pricing = "pricing"
    package = "package"
    faq = "faq"
    deposit_policy = "deposit_policy"
    cancellation_policy = "cancellation_policy"
    contract_terms = "contract_terms"
    service_description = "service_description"
    decoration_rules = "decoration_rules"
    catering_rules = "catering_rules"
    other = "other"


class DocumentStatus(str, enum.Enum):
    active = "active"
    archived = "archived"


class EmbeddingVector(UserDefinedType):
    cache_ok = True

    def get_col_spec(self, **kw) -> str:
        # Dimension is driven by EMBEDDING_DIM so the column always matches the
        # active embedding model (semantic or deterministic fallback).
        return f"vector({settings.embedding_dim})"

    def bind_processor(self, dialect):
        def process(value: list[float] | None) -> str | None:
            if value is None:
                return None
            return "[" + ",".join(str(float(item)) for item in value) + "]"

        return process

    def result_processor(self, dialect, coltype):
        def process(value: object) -> list[float] | None:
            if value is None:
                return None
            if isinstance(value, list):
                return [float(item) for item in value]
            if isinstance(value, str):
                text = value.strip()
                if text.startswith("["):
                    return [float(item) for item in json.loads(text)]
                return [float(item) for item in text.strip("()").split(",") if item]
            return None

        return process


class Document(TimestampMixin, Base):
    __tablename__ = "documents"
    __table_args__ = (
        Index("ix_documents_tenant_id", "tenant_id"),
        Index("ix_documents_tenant_id_document_type", "tenant_id", "document_type"),
        Index("ix_documents_tenant_id_status", "tenant_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    document_type: Mapped[DocumentType] = mapped_column(
        Enum(DocumentType, name="document_type"), nullable=False
    )
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus, name="document_status"),
        nullable=False,
        default=DocumentStatus.active,
    )
    uploaded_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False
    )


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        Index("ix_document_chunks_tenant_id", "tenant_id"),
        Index("ix_document_chunks_document_id", "document_id"),
        Index("ix_document_chunks_tenant_id_document_type", "tenant_id", "document_type"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    parent_chunk_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    parent_text: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_index: Mapped[int] = mapped_column(nullable=False)
    parent_chunk_index: Mapped[int] = mapped_column(nullable=False)
    document_title: Mapped[str] = mapped_column(String(255), nullable=False)
    document_type: Mapped[DocumentType] = mapped_column(
        Enum(DocumentType, name="document_type"), nullable=False
    )
    chunk_metadata: Mapped[dict[str, object]] = mapped_column(
        "metadata", JSON, nullable=False, default=dict
    )
    embedding: Mapped[list[float]] = mapped_column(EmbeddingVector, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
