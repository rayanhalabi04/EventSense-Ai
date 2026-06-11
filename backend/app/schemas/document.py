from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.document import DocumentStatus, DocumentType


class DocumentCreate(BaseModel):
    title: str
    document_type: DocumentType
    content_text: str
    original_filename: str | None = None
    status: DocumentStatus = DocumentStatus.active

    model_config = ConfigDict(extra="ignore")

    @field_validator("title", "content_text")
    @classmethod
    def validate_not_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value


class DocumentUpload(BaseModel):
    filename: str
    document_type: DocumentType
    content_text: str
    title: str | None = None

    model_config = ConfigDict(extra="ignore")


class DocumentUpdate(BaseModel):
    title: str | None = None
    document_type: DocumentType | None = None
    content_text: str | None = None
    status: DocumentStatus | None = None

    model_config = ConfigDict(extra="ignore")

    @field_validator("title", "content_text")
    @classmethod
    def validate_not_empty(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value


class DocumentRead(BaseModel):
    id: UUID
    tenant_id: UUID
    title: str
    document_type: DocumentType
    original_filename: str | None
    content_text: str
    status: DocumentStatus
    uploaded_by_user_id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
