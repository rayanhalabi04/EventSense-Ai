from collections.abc import Mapping
from typing import Any, Generic, TypeVar
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError


ModelT = TypeVar("ModelT")


class TenantScopedRepository(Generic[ModelT]):
    def __init__(self, model: type[ModelT], session: AsyncSession) -> None:
        self.model = model
        self.session = session

    async def list(self, tenant_id: UUID, **filters: Any) -> list[ModelT]:
        query = select(self.model).where(self.model.tenant_id == tenant_id)
        for field, value in filters.items():
            query = query.where(getattr(self.model, field) == value)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get(self, record_id: UUID, tenant_id: UUID) -> ModelT | None:
        result = await self.session.execute(
            select(self.model).where(self.model.id == record_id, self.model.tenant_id == tenant_id)
        )
        return result.scalar_one_or_none()

    async def get_or_403(self, record_id: UUID, tenant_id: UUID) -> ModelT:
        record = await self.get(record_id, tenant_id)
        if record is None:
            raise ForbiddenError()
        return record

    async def create(self, tenant_id: UUID, data: Mapping[str, Any]) -> ModelT:
        supplied_tenant_id = data.get("tenant_id")
        if supplied_tenant_id is not None and supplied_tenant_id != tenant_id:
            raise ForbiddenError()

        record = self.model(**{**dict(data), "tenant_id": tenant_id})
        self.session.add(record)
        await self.session.flush()
        return record

    async def update(self, record_id: UUID, tenant_id: UUID, data: Mapping[str, Any]) -> ModelT:
        record = await self.get_or_403(record_id, tenant_id)
        for field, value in data.items():
            if field == "tenant_id" and value != tenant_id:
                raise ForbiddenError()
            if field != "tenant_id":
                setattr(record, field, value)
        await self.session.flush()
        return record

    async def delete(self, record_id: UUID, tenant_id: UUID) -> None:
        record = await self.get_or_403(record_id, tenant_id)
        await self.session.delete(record)
        await self.session.flush()


def validate_same_tenant(*records: object) -> None:
    tenant_ids = {getattr(record, "tenant_id", None) for record in records}
    if None in tenant_ids or len(tenant_ids) > 1:
        raise ForbiddenError()
