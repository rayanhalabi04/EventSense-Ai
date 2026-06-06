from uuid import UUID

from pydantic import BaseModel, ConfigDict


class TenantRead(BaseModel):
    id: UUID
    name: str
    slug: str
    is_active: bool

    model_config = ConfigDict(from_attributes=True)
