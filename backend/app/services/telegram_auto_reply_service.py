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
from app.services.guardrail_service import SAFE_REFUSAL, check_input_guardrails, redact_pii
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
    r"^\s*here(?:'|’)?s a draft[^:]*:\s*",
    r"^\s*draft\s*:\s*",
    r"^\s*suggested reply\s*:\s*",
    r"^\s*you can reply\s*:\s*",
    r"^\s*staff can say\s*:\s*",
    r"^\s*for staff review\s*:?\s*",
)

# Telegram auto-replies are delivered straight to the client, so any internal
# "this is a draft / staff must approve" framing the generator added must be
# removed before sending. We drop whole sentences that contain these markers
# rather than just leading prefixes, because models often append the disclaimer
# at the end (e.g. "Staff review required before sending.") or mid-text.
STAFF_FACING_SENTENCE_MARKERS = (
    "staff review",
    "staff must review",
    "staff should review",
    "staff will review",
    "for staff review",
    "internal review",
    "internal note",
    "for internal use",
    "draft reply",
    "this is a draft",
    "a draft for",
    "draft for staff",
    "before sending",
    "needs approval",
    "need approval",
    "needs your approval",
    "requires approval",
    "pending approval",
    "no approval needed",
    "approval needed",
    "approval required",
    "sent automatically",
    "sent to the client automatically",
)

# Telegram is read on phones, so client replies must stay short. We trim long
# package detail down to the essentials and append a single warm closing line.
TELEGRAM_MAX_REPLY_CHARS = 600
# Telegram's own hard cap is 4096; used when delivering a staff/manual reply we
# must not over-summarize but still must keep within Telegram limits.
TELEGRAM_HARD_CHAR_LIMIT = 4096
TEAM_HELP_CLOSING = (
    "A member of our team can help you choose the best option based on your "
    "event needs."
)
# Sent instead of an incomplete/empty reply so a client never receives a
# mid-sentence fragment (see safe_trim_client_message).
SAFE_CLIENT_FALLBACK = (
    "Thank you for your message. A member of our team will review your request "
    "and follow up with you shortly."
)
_TERMINAL_PUNCTUATION = ".!?"
_CLOSING_WRAPPERS = "\"')]”’»"
# A trailing connector/preposition means the sentence was cut off; never end on
# one of these.
DANGLING_CONNECTOR_ENDINGS = (
    "and", "or", "but", "because", "with", "without", "to", "for", "of", "in",
    "on", "at", "by", "as", "if", "so", "that", "the", "a", "an", "once", "when",
    "while", "since", "however", "regarding", "including", "such as", "note that",
    "please note that", "according to",
)
# Detail lines clients don't need up front (they can ask, and a team member can
# walk them through extras). Dropped from the concise Telegram reply only — the
# dashboard draft keeps the full text.
ADDON_DETAIL_MARKERS = (
    "add-on",
    "add on",
    "addon",
    "overtime",
    "per hour",
    "per additional",
    "extra hour",
    "additional hour",
    "surcharge",
    "service charge",
    "service fee",
    "corkage",
    "gratuity",
    "per extra guest",
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
        # Record on the suggested reply that it was delivered automatically, so the
        # dashboard shows it as already sent instead of asking staff to approve it
        # again. Status is left untouched (human approval semantics are unchanged).
        suggested.auto_sent_at = now
        suggested.sent_channel = TELEGRAM_SOURCE
        session.add(suggested)
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
        """Deterministic pre-RAG eligibility check for auto-reply.

        Auto-reply is allowed only when ALL of these hold:
          * ``risk_level`` is "low" (risk detection is independent of intent),
          * ``intent_label`` is in the explicit allow-list of informational
            intents (pricing/availability/service/booking) and not in the
            blocked set (complaints, cancellations, payments, escalations…),
          * the body contains none of the risky keywords.

        Intent *confidence* is intentionally NOT a gate. The baseline TF-IDF
        classifier is poorly calibrated and emits 0.2–0.4 confidence for clear
        service/package questions, so a confidence threshold made auto-reply
        non-deterministic ("works in some cases"). The real safety nets are
        low-risk + allow-listed intent + RAG grounding + guardrails (the latter
        two enforced after generation in ``_generated_reply_skip_reason``).
        """
        if message.risk_level != "low":
            return "risk_not_low"
        if message.intent_label in AUTO_REPLY_BLOCKED_INTENTS:
            return "blocked_intent"
        if message.intent_label not in AUTO_REPLY_ALLOWED_INTENTS:
            return "intent_not_allowed"
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
    cleaned = _strip_staff_facing_prefixes(text)
    cleaned = telegram_plain_text(cleaned)
    cleaned = _strip_source_formatting_artifacts(cleaned)
    cleaned = _strip_staff_facing_sentences(cleaned)
    cleaned = redact_pii(cleaned)
    return _concise_telegram_reply(cleaned)


def _strip_staff_facing_prefixes(text: str) -> str:
    cleaned = (text or "").strip()
    changed = True
    while changed and cleaned:
        changed = False
        for pattern in STAFF_FACING_PREFIX_PATTERNS:
            stripped = re.sub(pattern, "", cleaned, count=1, flags=re.IGNORECASE)
            if stripped != cleaned:
                cleaned = stripped.strip()
                changed = True
                break
    return cleaned


def _strip_staff_facing_sentences(text: str) -> str:
    """Remove any sentence carrying internal staff/draft/approval framing.

    Operates line by line so multi-line content (e.g. package lists) keeps its
    structure. Blank lines are preserved as paragraph breaks; a line that becomes
    empty only because it was pure staff-facing meta is dropped entirely.
    """
    out_lines: list[str] = []
    for line in text.split("\n"):
        if not line.strip():
            out_lines.append("")
            continue
        kept = [
            sentence
            for sentence in re.split(r"(?<=[.!?])\s+", line)
            if not _is_staff_facing_sentence(sentence)
        ]
        joined = " ".join(part.strip() for part in kept if part.strip()).strip()
        if joined:
            out_lines.append(joined)
    cleaned = "\n".join(out_lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _strip_source_formatting_artifacts(text: str) -> str:
    """Remove document/source labels that should not be client-visible."""
    out_lines: list[str] = []
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            out_lines.append("")
            continue
        stripped = re.sub(
            r"(?i)\b(?:according to|based on)\s+our\s+[^:.\n]{1,80}:\s*",
            "",
            stripped,
        )
        stripped = re.sub(
            r"(?i)^(?:faq\s*:\s*)?q\s*:\s*.*?\?\s*(?:faq\s*:\s*)?a\s*:\s*",
            "",
            stripped,
        ).strip()
        stripped = re.sub(r"(?i)^(?:faq\s*:\s*)?q\s*:\s*", "", stripped).strip()
        if stripped.endswith("?"):
            continue
        stripped = re.sub(r"(?i)^(?:faq\s*:\s*)?a\s*:\s*", "", stripped).strip()
        stripped = re.sub(r"(?i)\b(?:q|a)\s*:\s*", "", stripped).strip()
        if stripped:
            out_lines.append(stripped)
    cleaned = "\n".join(out_lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _is_staff_facing_sentence(sentence: str) -> bool:
    lowered = sentence.lower()
    return any(marker in lowered for marker in STAFF_FACING_SENTENCE_MARKERS)


def _concise_telegram_reply(text: str) -> str:
    """Shape the cleaned reply into a short, mobile-friendly Telegram message.

    Drops long add-on/overtime/fee detail lines (pricing summarization), caps the
    overall length at a *safe sentence boundary*, and appends a single warm
    closing line. Returns ``""`` for empty/incomplete input so the caller skips
    sending (never sends a closing-only or mid-sentence message).
    """
    if not text.strip():
        return ""

    kept_lines = [
        line
        for line in text.split("\n")
        if not (line.strip() and _is_addon_detail_line(line))
    ]
    body = re.sub(r"\n{3,}", "\n\n", "\n".join(kept_lines)).strip()
    body = safe_trim_client_message(body, TELEGRAM_MAX_REPLY_CHARS)
    if not body:
        return ""

    if "member of our team can help you choose" not in body.lower():
        body = f"{body}\n\n{TEAM_HELP_CLOSING}"
    return body


def _is_addon_detail_line(line: str) -> bool:
    lowered = line.lower()
    return any(marker in lowered for marker in ADDON_DETAIL_MARKERS)


def staff_facing_telegram_text(text: str) -> str:
    """Format a staff/manual reply for Telegram delivery.

    Unlike the auto-reply path this does NOT apply pricing summarization (no
    dropping of add-on/fee lines, no auto closing) — it preserves the staff's
    answer, so cancellation/refund/policy replies keep their critical text. It
    still strips internal framing and guarantees the message is complete (never
    mid-sentence) and within Telegram's hard limit. Returns ``""`` when nothing
    complete remains, so the caller can substitute the safe fallback.
    """
    cleaned = _strip_staff_facing_prefixes(text)
    cleaned = telegram_plain_text(cleaned)
    cleaned = _strip_source_formatting_artifacts(cleaned)
    cleaned = _strip_staff_facing_sentences(cleaned)
    cleaned = redact_pii(cleaned)
    return safe_trim_client_message(cleaned, TELEGRAM_HARD_CHAR_LIMIT)


def _ends_completely(text: str) -> bool:
    """True if ``text`` ends with sentence-terminal punctuation."""
    stripped = text.rstrip().rstrip(_CLOSING_WRAPPERS).rstrip()
    return bool(stripped) and stripped[-1] in _TERMINAL_PUNCTUATION


def _has_internal_terminator(text: str) -> bool:
    return any(ch in text for ch in _TERMINAL_PUNCTUATION)


def safe_trim_client_message(text: str, max_chars: int) -> str:
    """Return a complete, client-safe message within ``max_chars``.

    Guarantees:
      * never cuts mid-sentence — trims only at sentence / line boundaries;
      * an input that was truncated mid-sentence upstream (a dangling fragment,
        e.g. "...Please note that once a") yields ``""`` so the caller can send a
        safe fallback instead of a partial/incomplete answer;
      * the returned text always ends with terminal punctuation.

    Returns ``""`` when no complete, substantive message can be produced.
    """
    cleaned = (text or "").strip()
    if not cleaned:
        return ""

    # A short, single-clause message with no sentence punctuation (e.g. "Sounds
    # good") is treated as complete — don't mangle legitimate brief staff replies.
    if (
        "\n" not in cleaned
        and not _has_internal_terminator(cleaned)
        and len(cleaned) <= 80
    ):
        return cleaned

    # Truncated upstream: ends without terminal punctuation -> don't risk
    # delivering a content-stripped remainder. Signal the caller to use a fallback.
    if not _ends_completely(cleaned):
        return ""

    if len(cleaned) <= max_chars:
        return cleaned

    return _trim_complete_to_budget(cleaned, max_chars)


def _trim_complete_to_budget(text: str, max_chars: int) -> str:
    """Drop whole trailing sentences/lines until within budget (never mid-sentence)."""
    out_lines: list[str] = []
    total = 0
    for line in text.split("\n"):
        if not line.strip():
            if out_lines:
                out_lines.append("")
                total += 1
            continue
        kept_sentences: list[str] = []
        line_len = 0
        for sentence in re.split(r"(?<=[.!?])\s+", line.strip()):
            if not _ends_completely(sentence):
                continue  # skip a dangling fragment within the line
            addition = len(sentence) + (1 if kept_sentences else 0)
            projected = total + line_len + addition + (1 if out_lines else 0)
            if (kept_sentences or out_lines) and projected > max_chars:
                break
            kept_sentences.append(sentence)
            line_len += addition
        if not kept_sentences:
            break
        out_lines.append(" ".join(kept_sentences))
        total += line_len + (1 if len(out_lines) > 1 else 0)
    result = re.sub(r"\n{3,}", "\n\n", "\n".join(out_lines)).strip()
    if not result or not _ends_completely(result):
        return ""
    return result


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
