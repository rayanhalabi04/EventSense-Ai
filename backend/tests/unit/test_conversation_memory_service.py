from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.services.conversation_memory_service import (
    ConversationMemoryMessage,
    ConversationMemoryService,
    _redact_sensitive_text,
)


pytestmark = pytest.mark.asyncio


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, list[str]] = {}
        self.ttls: dict[str, int] = {}

    async def lpush(self, key: str, *values: str) -> None:
        self.store.setdefault(key, [])
        self.store[key] = list(values) + self.store[key]

    async def ltrim(self, key: str, start: int, end: int) -> None:
        self.store[key] = self.store.get(key, [])[start : end + 1]

    async def expire(self, key: str, time: int) -> None:
        self.ttls[key] = time

    async def lrange(self, key: str, start: int, end: int) -> list[str]:
        return self.store.get(key, [])[start : end + 1]


class FailingRedis:
    async def lpush(self, key: str, *values: str) -> None:
        raise ConnectionError("redis down")

    async def ltrim(self, key: str, start: int, end: int) -> None:
        raise ConnectionError("redis down")

    async def expire(self, key: str, time: int) -> None:
        raise ConnectionError("redis down")

    async def lrange(self, key: str, start: int, end: int) -> list[str]:
        raise ConnectionError("redis down")


async def test_memory_uses_tenant_and_conversation_scoped_keys() -> None:
    redis = FakeRedis()
    tenant_a = uuid4()
    tenant_b = uuid4()
    conversation_id = uuid4()
    service = ConversationMemoryService(
        redis_client=redis,
        enabled=True,
        ttl_seconds=604800,
        max_messages=10,
    )

    await service.store_message(
        tenant_id=tenant_a,
        conversation_id=conversation_id,
        memory=ConversationMemoryMessage(
            message_id=str(uuid4()),
            direction="inbound",
            body="Tenant A question",
            sent_at=datetime.now(timezone.utc).isoformat(),
        ),
    )

    assert await service.load_recent(tenant_id=tenant_a, conversation_id=conversation_id)
    assert await service.load_recent(tenant_id=tenant_b, conversation_id=conversation_id) == []


async def test_memory_applies_ttl_and_max_messages() -> None:
    redis = FakeRedis()
    tenant_id = uuid4()
    conversation_id = uuid4()
    service = ConversationMemoryService(
        redis_client=redis,
        enabled=True,
        ttl_seconds=123,
        max_messages=2,
    )

    for index in range(3):
        await service.store_message(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            memory=ConversationMemoryMessage(
                message_id=str(uuid4()),
                direction="inbound",
                body=f"Message {index}",
                sent_at=datetime.now(timezone.utc).isoformat(),
            ),
        )

    key = ConversationMemoryService.key(tenant_id, conversation_id)
    loaded = await service.load_recent(tenant_id=tenant_id, conversation_id=conversation_id)

    assert redis.ttls[key] == 123
    assert [message.body for message in loaded] == ["Message 1", "Message 2"]


async def test_redis_failures_return_empty_memory_without_raising() -> None:
    service = ConversationMemoryService(
        redis_client=FailingRedis(),
        enabled=True,
        ttl_seconds=604800,
        max_messages=10,
    )

    await service.store_message(
        tenant_id=uuid4(),
        conversation_id=uuid4(),
        memory=ConversationMemoryMessage(
            message_id=str(uuid4()),
            direction="inbound",
            body="Still should not raise",
            sent_at=datetime.now(timezone.utc).isoformat(),
        ),
    )

    assert await service.load_recent(tenant_id=uuid4(), conversation_id=uuid4()) == []


async def test_memory_redacts_obvious_secret_values() -> None:
    text = _redact_sensitive_text("api_key=sk-test password:super-secret Bearer abcdefghijklmnop")

    assert "sk-test" not in text
    assert "super-secret" not in text
    assert "abcdefghijklmnop" not in text
    assert "<REDACTED>" in text
