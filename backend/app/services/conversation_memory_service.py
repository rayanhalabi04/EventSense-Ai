from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import UUID

from app.core.config import settings
from app.models.message import Message, MessageDirection


logger = logging.getLogger(__name__)


class RedisClient(Protocol):
    async def ping(self) -> Any:
        ...

    async def lpush(self, key: str, *values: str) -> Any:
        ...

    async def ltrim(self, key: str, start: int, end: int) -> Any:
        ...

    async def expire(self, key: str, time: int) -> Any:
        ...

    async def lrange(self, key: str, start: int, end: int) -> list[Any]:
        ...


_redis_client: RedisClient | None = None


@dataclass(frozen=True)
class ConversationMemoryMessage:
    message_id: str
    direction: str
    body: str
    sent_at: str


class ConversationMemoryService:
    def __init__(
        self,
        *,
        redis_client: RedisClient | None = None,
        enabled: bool | None = None,
        ttl_seconds: int | None = None,
        max_messages: int | None = None,
    ) -> None:
        self.redis_client = redis_client
        self.enabled = settings.memory_enabled if enabled is None else enabled
        self.ttl_seconds = (
            settings.short_term_memory_ttl_seconds if ttl_seconds is None else ttl_seconds
        )
        self.max_messages = (
            settings.short_term_memory_max_messages if max_messages is None else max_messages
        )

    @staticmethod
    def key(tenant_id: UUID, conversation_id: UUID) -> str:
        return f"tenant:{tenant_id}:conversation:{conversation_id}:memory"

    async def store_inbound_message(self, *, tenant_id: UUID, message: Message) -> None:
        if message.direction is not MessageDirection.inbound:
            return
        await self.store_message(
            tenant_id=tenant_id,
            conversation_id=message.conversation_id,
            memory=ConversationMemoryMessage(
                message_id=str(message.id),
                direction=message.direction.value,
                body=_redact_sensitive_text(message.body),
                sent_at=_isoformat(message.sent_at),
            ),
        )

    async def store_message(
        self,
        *,
        tenant_id: UUID,
        conversation_id: UUID,
        memory: ConversationMemoryMessage,
    ) -> None:
        if not self._usable():
            return
        client = self.redis_client or _get_redis_client()
        if client is None:
            return
        key = self.key(tenant_id, conversation_id)
        try:
            await client.lpush(key, json.dumps(asdict(memory)))
            await client.ltrim(key, 0, self.max_messages - 1)
            await client.expire(key, self.ttl_seconds)
        except Exception:
            logger.warning("conversation memory write failed", exc_info=True)

    async def load_recent(
        self,
        *,
        tenant_id: UUID,
        conversation_id: UUID,
    ) -> list[ConversationMemoryMessage]:
        if not self._usable():
            return []
        client = self.redis_client or _get_redis_client()
        if client is None:
            return []
        key = self.key(tenant_id, conversation_id)
        try:
            raw_items = await client.lrange(key, 0, self.max_messages - 1)
        except Exception:
            logger.warning("conversation memory read failed", exc_info=True)
            return []

        messages: list[ConversationMemoryMessage] = []
        for item in reversed(raw_items):
            try:
                if isinstance(item, bytes):
                    item = item.decode("utf-8")
                data = json.loads(str(item))
                messages.append(
                    ConversationMemoryMessage(
                        message_id=str(data["message_id"]),
                        direction=str(data["direction"]),
                        body=str(data["body"]),
                        sent_at=str(data["sent_at"]),
                    )
                )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                continue
        return messages

    def _usable(self) -> bool:
        return self.enabled and bool(settings.redis_url.strip()) and self.max_messages > 0


async def get_memory_status() -> str:
    if not settings.memory_enabled:
        return "disabled"
    if not settings.redis_url.strip():
        return "unavailable"
    client = _get_redis_client()
    if client is None:
        return "unavailable"
    try:
        await client.ping()
    except Exception:
        logger.warning("conversation memory redis health check failed", exc_info=True)
        return "unavailable"
    return "ok"


def _get_redis_client() -> RedisClient | None:
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    try:
        from redis.asyncio import Redis
    except ImportError:
        logger.warning("conversation memory enabled but redis package is not installed")
        return None
    try:
        _redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
    except Exception:
        logger.warning("conversation memory redis client initialization failed", exc_info=True)
        return None
    return _redis_client


def _isoformat(value: datetime | None) -> str:
    if value is None:
        value = datetime.now(timezone.utc)
    return value.isoformat()


_SECRET_PATTERNS = (
    re.compile(r"(?i)\b(api[_ -]?key|secret|token|password)\s*[:=]\s*([^\s,;]+)"),
    re.compile(r"(?i)\bbearer\s+([A-Za-z0-9._~+/=-]{12,})"),
)


def _redact_sensitive_text(text: str) -> str:
    redacted = text
    redacted = _SECRET_PATTERNS[0].sub(lambda match: f"{match.group(1)}=<REDACTED>", redacted)
    redacted = _SECRET_PATTERNS[1].sub("Bearer <REDACTED>", redacted)
    return redacted
