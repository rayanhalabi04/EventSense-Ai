from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.task import TaskStatus


class TaskCreate(BaseModel):
    conversation_id: UUID
    message_id: UUID | None = None
    title: str
    description: str | None = None
    assigned_to_user_id: UUID | None = None
    due_at: datetime | None = None
    status: TaskStatus = TaskStatus.open

    model_config = ConfigDict(extra="ignore")


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    assigned_to_user_id: UUID | None = None
    due_at: datetime | None = None
    status: TaskStatus | None = None

    model_config = ConfigDict(extra="ignore")


class TaskRead(BaseModel):
    id: UUID
    tenant_id: UUID
    conversation_id: UUID
    message_id: UUID | None
    title: str
    description: str | None
    assigned_to_user_id: UUID | None
    due_at: datetime | None
    status: TaskStatus
    created_by_user_id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
