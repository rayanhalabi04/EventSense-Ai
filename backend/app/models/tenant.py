import enum
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Enum, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.core.database import Base, TimestampMixin


class TenantKind(str, enum.Enum):
    customer = "customer"
    platform = "platform"


class Tenant(TimestampMixin, Base):
    __tablename__ = "tenants"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    kind: Mapped[TenantKind] = mapped_column(
        Enum(TenantKind, name="tenant_kind"), nullable=False, default=TenantKind.customer
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    users = relationship("User", back_populates="tenant")
    conversations = relationship("Conversation", back_populates="tenant")
