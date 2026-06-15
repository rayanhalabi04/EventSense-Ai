from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.conversation import Conversation
from app.models.message import Message, MessageDirection
from app.models.suggested_reply import SuggestedReply
from app.repositories.message_repository import MessageRepository
from app.repositories.tenant_repository import TenantRepository
from app.services.audit_log_service import (
    AUDIT_EVENT_TELEGRAM_AUTO_REPLY_SENT,
    AUDIT_EVENT_TELEGRAM_AUTO_REPLY_SKIPPED,
    AuditLogService,
)
from app.services.guardrail_service import SAFE_REFUSAL, check_input_guardrails
from app.services.suggested_reply_service import generate_suggested_reply
from app.services.telegram_service import TELEGRAM_SOURCE, TelegramApiError, TelegramService


AUTO_REPLY_ALLOWED_INTENTS = {
    "pricing_request",
    "availability_question",
    "service_question",
    "booking_inquiry",
}
AUTO_REPLY_BLOCKED_INTENTS = {
    "payment_issue",
    "cancellation_request",
    "complaint",
    "urgent_change",
    "guest_count_change",
    "human_escalation",
    "other",
}
AUTO_REPLY_MIN_CONFIDENCE = 0.70
AUTO_REPLY_RISKY_KEYWORDS = (
    "payment",
    "paid",
    "charge",
    "charged",
    "cancellation",
    "cancel",
    "refund",
    "complaint",
    "complain",
    "urgent",
    "asap",
    "immediately",
    "manager",
    "human",
    "angry",
    "deposit issue",
    "contract dispute",
    "lawyer",
    "legal",
    "lawsuit",
    "attorney",
)
STAFF_FACING_PREFIX_PATTERNS = (
    r"^\s*here(?:'|’)?s a draft for staff review\s*:\s*",
    r"^\s*draft\s*:\s*",
    r"^\s*suggested reply\s*:\s*",
    r"^\s*you can reply\s*:\s*",
    r"^\s*staff can say\s*:\s*",
    r"^\s*for staff review\s*:?\s*",
)


@dataclass(frozen=True)
class AutoReplyDecision:
    sent: bool
    reason: str | None
    suggested_reply: SuggestedReply | None = None
    outbound_message: Message | None = None


class TelegramAutoReplyService:
    def __init__(self, telegram: TelegramService | None = None) -> None:
        self.telegram = telegram or TelegramService()

    async def maybe_auto_reply(
        self,
        session: AsyncSession,
        *,
        conversation: Conversation,
        message: Message,
    ) -> AutoReplyDecision:
        if message.source != TELEGRAM_SOURCE or message.direction != MessageDirection.inbound:
            return AutoReplyDecision(sent=False, reason="not_telegram_inbound")

        if not settings.telegram_auto_reply_enabled:
            await self._record_skip(session, conversation, message, "auto_reply_disabled")
            return AutoReplyDecision(sent=False, reason="auto_reply_disabled")

        preliminary_reason = self._preliminary_skip_reason(message)
        if preliminary_reason is not None:
            suggested = await self._generate_staff_draft(session, conversation, message)
            await self._record_skip(session, conversation, message, preliminary_reason, suggested)
            return AutoReplyDecision(sent=False, reason=preliminary_reason, suggested_reply=suggested)

        tenant_slug = await TenantRepository(session).get_slug(message.tenant_id)
        input_guardrail = check_input_guardrails(message.body, tenant_slug)
        if not input_guardrail.allowed:
            suggested = await self._generate_staff_draft(session, conversation, message)
            await self._record_skip(session, conversation, message, "guardrail_refusal", suggested)
            return AutoReplyDecision(sent=False, reason="guardrail_refusal", suggested_reply=suggested)

        suggested = await self._generate_staff_draft(session, conversation, message)
        generated_skip_reason = self._generated_reply_skip_reason(suggested)
        if generated_skip_reason is not None:
            await self._record_skip(session, conversation, message, generated_skip_reason, suggested)
            return AutoReplyDecision(
                sent=False,
                reason=generated_skip_reason,
                suggested_reply=suggested,
            )
        client_text = client_facing_auto_reply_text(suggested.suggested_text)
        if not client_text:
            await self._record_skip(session, conversation, message, "client_reply_empty", suggested)
            return AutoReplyDecision(
                sent=False,
                reason="client_reply_empty",
                suggested_reply=suggested,
            )

        try:
            telegram_response = await self.telegram.send_message(
                conversation.external_conversation_id or conversation.client_contact or "",
                client_text,
            )
        except TelegramApiError:
            await self._record_skip(session, conversation, message, "telegram_send_failed", suggested)
            return AutoReplyDecision(
                sent=False,
                reason="telegram_send_failed",
                suggested_reply=suggested,
            )

        telegram_message_id = _sent_message_id(telegram_response)
        now = datetime.now(timezone.utc)
        conversation.updated_at = now
        outbound = Message(
            tenant_id=message.tenant_id,
            conversation_id=conversation.id,
            direction=MessageDirection.outbound,
            body=client_text,
            source=TELEGRAM_SOURCE,
            external_message_id=telegram_message_id,
            sender_user_id=None,
            sent_at=now,
        )
        await MessageRepository(session).add(outbound)
        AuditLogService.record(
            session,
            tenant_id=message.tenant_id,
            actor_user_id=None,
            event_type=AUDIT_EVENT_TELEGRAM_AUTO_REPLY_SENT,
            resource_type="message",
            resource_id=outbound.id,
            details={
                "conversation_id": conversation.id,
                "inbound_message_id": message.id,
                "suggested_reply_id": suggested.id,
                "telegram_message_id": telegram_message_id,
                "source_document_ids": suggested.source_document_ids,
            },
        )
        await session.commit()
        await session.refresh(outbound)
        return AutoReplyDecision(sent=True, reason=None, suggested_reply=suggested, outbound_message=outbound)

    @staticmethod
    def _preliminary_skip_reason(message: Message) -> str | None:
        if message.risk_level != "low":
            return "risk_not_low"
        if message.intent_label in AUTO_REPLY_BLOCKED_INTENTS:
            return "blocked_intent"
        if message.intent_label not in AUTO_REPLY_ALLOWED_INTENTS:
            return "intent_not_allowed"
        if message.intent_confidence is None or message.intent_confidence < AUTO_REPLY_MIN_CONFIDENCE:
            return "low_confidence"
        if _contains_risky_keyword(message.body):
            return "risky_keyword"
        return None

    @staticmethod
    def _generated_reply_skip_reason(suggested: SuggestedReply) -> str | None:
        if not suggested.answer_supported or not suggested.rag_sources:
            if suggested.refusal_reason == SAFE_REFUSAL:
                return "guardrail_refusal"
            return "no_rag_source"
        if not suggested.suggested_text.strip():
            return "suggested_reply_empty"
        return None

    @staticmethod
    async def _generate_staff_draft(
        session: AsyncSession,
        conversation: Conversation,
        message: Message,
    ) -> SuggestedReply:
        return await generate_suggested_reply(
            session,
            tenant_id=message.tenant_id,
            user_id=None,
            conversation=conversation,
            message=message,
        )

    @staticmethod
    async def _record_skip(
        session: AsyncSession,
        conversation: Conversation,
        message: Message,
        reason: str,
        suggested_reply: SuggestedReply | None = None,
    ) -> None:
        AuditLogService.record(
            session,
            tenant_id=message.tenant_id,
            actor_user_id=None,
            event_type=AUDIT_EVENT_TELEGRAM_AUTO_REPLY_SKIPPED,
            resource_type="message",
            resource_id=message.id,
            details={
                "conversation_id": conversation.id,
                "message_id": message.id,
                "reason": reason,
                "risk_level": message.risk_level,
                "intent_label": message.intent_label,
                "intent_confidence": message.intent_confidence,
                "suggested_reply_id": suggested_reply.id if suggested_reply is not None else None,
            },
        )
        await session.commit()


def _contains_risky_keyword(text: str) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in AUTO_REPLY_RISKY_KEYWORDS)


def client_facing_auto_reply_text(text: str) -> str:
    cleaned = text.strip()
    changed = True
    while changed and cleaned:
        changed = False
        for pattern in STAFF_FACING_PREFIX_PATTERNS:
            stripped = re.sub(pattern, "", cleaned, count=1, flags=re.IGNORECASE)
            if stripped != cleaned:
                cleaned = stripped.strip()
                changed = True
                break
    return telegram_plain_text(cleaned)


def telegram_plain_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    lines: list[str] = []
    for raw_line in text.split("\n"):
        line = raw_line.strip()
        line = re.sub(r"^[*-]\s+", "", line)
        line = re.sub(r"\s+", " ", line).strip()
        lines.append(line)
    cleaned = "\n".join(lines).strip()
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned


def _sent_message_id(response: dict[str, object]) -> str | None:
    result = response.get("result")
    if isinstance(result, dict) and result.get("message_id") is not None:
        return str(result["message_id"])
    return None
