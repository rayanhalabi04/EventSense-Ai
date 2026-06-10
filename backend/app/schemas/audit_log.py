from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AuditLogRead(BaseModel):
    id: UUID
    tenant_id: UUID
    actor_user_id: UUID | None
    event_type: str
    resource_type: str | None
    resource_id: str | None
    details: dict[str, object]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
