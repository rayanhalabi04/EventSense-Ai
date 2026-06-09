from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.tenant import TenantKind


class TenantRead(BaseModel):
    id: UUID
    name: str
    slug: str
    kind: TenantKind
    is_active: bool

    model_config = ConfigDict(from_attributes=True)
