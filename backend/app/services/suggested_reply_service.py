"""Suggested reply generation.

Suggested replies are drafted for *staff review only* — they are never sent to
clients automatically. A reply is grounded strictly in the tenant's own RAG
sources; if retrieval returns nothing, the service produces a polite refusal
that recommends staff/manager review instead of inventing policy.

The default generator is a deterministic, template-based builder
(``template_v1``) so the feature works without any paid LLM API and so tests are
fully reproducible. A hosted-LLM generator can be added later behind
``settings.llm_enabled`` without changing the public API contract.
"""
import re
from dataclasses import dataclass
from typing import Callable, Sequence
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.models.message import Message
from app.models.suggested_reply import SuggestedReply, SuggestedReplyStatus
from app.core.tenant_context import TenantContext
from app.repositories.message_repository import MessageRepository
from app.repositories.suggested_reply_repository import SuggestedReplyRepository
from app.repositories.tenant_repository import TenantRepository
from app.services.calendar_availability_parser import (
    is_availability_question,
    parse_availability_request,
)
from app.services.calendar_service import CalendarService
from app.services.audit_log_service import (
    AUDIT_EVENT_SUGGESTED_REPLY_APPROVED,
    AUDIT_EVENT_SUGGESTED_REPLY_EDITED,
    AUDIT_EVENT_SUGGESTED_REPLY_GENERATED,
    AUDIT_EVENT_SUGGESTED_REPLY_REJECTED,
    AUDIT_EVENT_SUGGESTED_REPLY_REFUSED_NO_SOURCE,
    AuditLogService,
)
from app.services.guardrail_service import (
    SAFE_REFUSAL,
    GuardrailResult,
    apply_guardrails_to_suggested_reply,
    audit_guardrail_event,
    check_input_guardrails,
    check_output_guardrails,
    check_retrieval_guardrails,
    redact_pii,
)
from app.services.llm_service import (
    LLMClient,
    LLMReplyRequest,
    LLMSmallTalkRequest,
    get_llm_client,
)
from app.schemas.suggested_reply import SuggestedReplyUpdate
from app.services.conversation_memory_service import (
    ConversationMemoryMessage,
    ConversationMemoryService,
)
from app.services.rag_service import RagResult, retrieve


GENERATION_METHOD_TEMPLATE = "template_v1"
GENERATION_METHOD_LLM = "llm_v1"
GENERATION_METHOD_CALENDAR_AVAILABILITY = "calendar_availability_v1"
GENERATION_METHOD_SMALL_TALK_PREFIX = "small_talk_"
GENERATION_METHOD_SMALL_TALK_SUFFIX = "_v1"
SMALL_TALK_LLM_CATEGORY = "llm_safe_casual"
SMALL_TALK_LLM_GENERIC_REPLY = "Thank you. Let us know if you need anything else."

REFUSAL_TEXT = (
    "Hi, thank you for your message. I could not find enough information in our "
    "uploaded company documents to answer this confidently. I'll ask a staff "
    "member to review this and follow up, and a manager can step in if needed."
)
REFUSAL_REASON = (
    "No supporting information was found in the tenant's uploaded documents for "
    "this question."
)

GREETING = "Hi, thank you for your message."
ESCALATION_SENTENCE = (
    "If you would like us to review a special case, I can escalate this to a "
    "manager for review."
)
PRICING_FOLLOWUP_SENTENCE = (
    "A member of our team can help you choose the best option based on your "
    "event needs."
)
INTENT_FOLLOWUP_SENTENCES = {
    "pricing_request": PRICING_FOLLOWUP_SENTENCE,
    "booking_inquiry": (
        "A member of our team can guide you through the next steps and confirm "
        "the details needed to start your booking."
    ),
    "availability_question": "A member of our team will check availability and follow up with you.",
    "service_question": (
        "A member of our team can share more details and help confirm the "
        "services that fit your event."
    ),
    "guest_count_change": (
        "A member of our team will review your booking details and confirm what "
        "changes are still possible."
    ),
    "urgent_change": "A member of our team will review this urgently and follow up with the next steps.",
    "cancellation_request": (
        "A member of our team will review your booking details and follow up "
        "with the cancellation next steps."
    ),
    "complaint": "A manager or team member will review this carefully and follow up with you shortly.",
    "payment_issue": "A member of our team will verify the payment status and update you as soon as possible.",
    "human_escalation": "A team member will review your request and follow up with you directly.",
    "other": "A team member will review your request and follow up with you.",
}
DEFAULT_FOLLOWUP_SENTENCE = INTENT_FOLLOWUP_SENTENCES["other"]
PAYMENT_VERIFICATION_REPLY = (
    "Hi, thank you for your message. "
    f"{INTENT_FOLLOWUP_SENTENCES['payment_issue']}"
)
PAYMENT_VERIFICATION_REFUSAL_REASON = "Payment confirmation requires staff verification."
CONTACT_FOLLOWUP_REPLY = (
    "Thank you. I'll ask a team member to contact you about your booking."
)
CONTACT_FOLLOWUP_REFUSAL_REASON = "Contact requests require staff follow-up."
GUEST_COUNT_REVIEW_REFUSAL_REASON = "Guest count/capacity changes require staff review."
HIGH_RISK_REVIEW_REFUSAL_REASON = "High-risk complaint or human escalation requires staff review."
AVAILABILITY_PARSE_REFUSAL_REASON = "Availability request needs a specific date and time."
AVAILABILITY_MANUAL_REVIEW_REASON = "Calendar availability requires staff review."
SMALL_TALK_CONTEXTUAL_MEETING_REPLY = (
    "You're welcome. We look forward to speaking with you then."
)
SMALL_TALK_REPLIES = {
    "greeting": "Hi, how can we help you today?",
    "thanks": "You're very welcome. Let us know if you need anything else.",
    "acknowledgement": "Great, thank you.",
    "closing": "Thank you. Have a great day.",
}

_ESCALATION_KEYWORDS = (
    "cancel",
    "cancellation",
    "refund",
    "refundable",
    "non-refundable",
    "dispute",
    "complaint",
    "lawyer",
)

_PAYMENT_VERIFICATION_TERMS = (
    "paid",
    "payment",
    "deposit",
    "invoice",
    "receipt",
    "confirmed",
    "confirmation",
    "check",
    "verify",
    "update",
)

_REFUND_OR_CANCELLATION_TERMS = (
    "cancel",
    "cancellation",
    "refund",
    "refundable",
    "non-refundable",
)
_DEPOSIT_REFUND_QUESTION_TERMS = _REFUND_OR_CANCELLATION_TERMS + (
    "deposit",
    "booking terms",
)

_FOLLOWUP_REFERENCE_PATTERN = re.compile(
    r"\b(that|this|it)\b|\bthe\s+change\b|\bchange\s+the\s+price\b",
    re.IGNORECASE,
)
_PRICE_OR_INVOICE_PATTERN = re.compile(
    r"\b(price|prices|pricing|cost|costs|rate|rates|invoice|balance|quote|quoted)\b",
    re.IGNORECASE,
)
_REFERENCE_REPLACEMENTS = (
    re.compile(r"\bthe\s+change\b", re.IGNORECASE),
    re.compile(r"\b(that|this|it)\b", re.IGNORECASE),
)
_GUEST_COUNT_CHANGE_PATTERN = re.compile(
    r"\b(?:change|changing|update|updating|increase|increasing|raise|raising|adjust|adjusting)"
    r"\s+(?:the\s+)?(?:guest\s+count|headcount|guests?)\s+from\s+(\d+)\s+to\s+(\d+)\b",
    re.IGNORECASE,
)
_GUEST_COUNT_FROM_TO_PATTERN = re.compile(
    r"\bfrom\s+(\d+)\s+(?:guests?|people|pax)?\s+to\s+(\d+)\s+(?:guests?|people|pax)?\b",
    re.IGNORECASE,
)
_GUEST_COUNT_OPERATIONAL_PATTERNS = (
    re.compile(r"\bextra\s+guests?\b", re.IGNORECASE),
    re.compile(r"\badditional\s+guests?\b", re.IGNORECASE),
    re.compile(r"\bmore\s+guests?\b", re.IGNORECASE),
    re.compile(r"\badd(?:ing)?\s+\d+\s+(?:more\s+|additional\s+|extra\s+)?guests?\b", re.IGNORECASE),
    re.compile(r"\badd(?:ing)?\s+(?:more\s+|additional\s+|extra\s+)?guests?\b", re.IGNORECASE),
    re.compile(r"\bincrease\s+(?:the\s+)?(?:guest\s+count|guests?)\b", re.IGNORECASE),
    re.compile(r"\bguest\s+count\b", re.IGNORECASE),
    re.compile(r"\bheadcount\b", re.IGNORECASE),
    re.compile(r"\b(?:venue|catering|seating)\s+capacity\b", re.IGNORECASE),
    re.compile(r"\bcapacity\s+for\s+\d+\s+guests?\b", re.IGNORECASE),
    re.compile(r"\bhandle\s+\d+\s+(?:more\s+|additional\s+|extra\s+)?guests?\b", re.IGNORECASE),
)
_COMPLAINT_TERMS = (
    "complaint",
    "complain",
    "unhappy",
    "upset",
    "disappointed",
    "bad service",
    "unacceptable",
    "wrong",
)
_HUMAN_ESCALATION_TERMS = (
    "manager",
    "supervisor",
    "human",
    "person",
    "agent",
)
_CONTACT_FOLLOWUP_PATTERNS = (
    re.compile(r"\bcontact\s+me\b", re.IGNORECASE),
    re.compile(r"\bhave\s+someone\s+contact\s+me\b", re.IGNORECASE),
    re.compile(r"\bsomeone\s+contact\s+me\b", re.IGNORECASE),
    re.compile(r"\bcall\s+me\b", re.IGNORECASE),
    re.compile(r"\breach\s+(?:out\s+)?to\s+me\b", re.IGNORECASE),
    re.compile(r"\bget\s+in\s+touch\s+with\s+me\b", re.IGNORECASE),
)
_OLD_GENERIC_FOLLOWUP_SENTENCES = (
    PRICING_FOLLOWUP_SENTENCE,
    "We would be happy to help you choose the best option.",
    "We would be happy to help you choose the best option for your event.",
    "We would be happy to help you choose the best option based on your event needs.",
    "We'd be happy to help you choose the best option.",
    "We'd be happy to help you choose the best option for your event.",
    "A team member can help you choose the best option.",
    "A team member can help you choose the best option based on your event needs.",
    "Our team will review your request and follow up with you.",
    "A member of our team will review your request and follow up with the details.",
    "A member of our team will review your request and follow up with you shortly.",
    "A team member will follow up with you shortly.",
)
_GENERIC_FOLLOWUP_STARTS = (
    "a member of our team",
    "a team member",
    "our team",
    "a manager or team member",
    "we would be happy",
    "we'd be happy",
)
_GENERIC_FOLLOWUP_MARKERS = (
    "help you choose",
    "choose the best option",
    "share more details",
    "share the full details",
    "confirm the details",
    "confirm whether",
    "guide you through",
    "check availability",
    "verify the payment",
    "review your request",
    "review your booking",
    "follow up",
)

_SMALL_TALK_PHRASES = {
    "closing": {
        "bye",
        "goodbye",
        "ok bye",
        "okay bye",
        "see you",
        "talk later",
    },
    "thanks": {
        "thank you",
        "thanks",
        "thx",
        "merci",
    },
    "greeting": {
        "hello",
        "hey",
        "good morning",
        "good evening",
    },
    "acknowledgement": {
        "ok",
        "okay",
        "noted",
        "sure",
        "great",
        "perfect",
    },
}
_SMALL_TALK_ORDER = ("closing", "thanks", "greeting", "acknowledgement")
_MEETING_CONFIRMATION_TERMS = (
    "meeting",
    "call",
    "appointment",
    "speaking with you",
    "speak with you",
)
_EVENT_TYPE_TERMS = (
    ("wedding", "wedding"),
    ("reception", "reception"),
    ("engagement", "engagement"),
    ("bridal shower", "bridal shower"),
    ("corporate dinner", "corporate dinner"),
    ("birthday", "birthday"),
    ("ceremony", "ceremony"),
)
_MONTH_DATE_PATTERN = re.compile(
    r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|"
    r"dec(?:ember)?)\s+\d{1,2}(?:st|nd|rd|th)?(?:,\s*\d{4})?\b",
    re.IGNORECASE,
)
_DAY_MONTH_DATE_PATTERN = re.compile(
    r"\b\d{1,2}(?:st|nd|rd|th)?\s+(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|"
    r"apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|"
    r"oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)(?:,?\s*\d{4})?\b",
    re.IGNORECASE,
)
_NUMERIC_DATE_PATTERN = re.compile(r"\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b")
_RELATIVE_DATE_PATTERN = re.compile(
    r"\b(?:today|tomorrow|tonight|this\s+week|next\s+week|"
    r"(?:this|next)\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)|"
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    re.IGNORECASE,
)
_CONFIRMED_MEETING_TERMS = (
    "confirmed",
    "confirm",
    "scheduled",
    "works for us",
    "see you",
    "speak with you then",
    "speaking with you then",
)
_SMALL_TALK_LLM_BLOCK_PATTERNS = (
    r"\bpricing\b",
    r"\bprices?\b",
    r"\bpackages?\b",
    r"\bcosts?\b",
    r"\bquotes?\b",
    r"\bdeposit\b",
    r"\brefunds?\b",
    r"\bcancell?ation\b",
    r"\bcancell?ed\b",
    r"\bcancell?ing\b",
    r"\bcancel\b",
    r"\bpayments?\b",
    r"\bpaid\b",
    r"\binvoices?\b",
    r"\breceipts?\b",
    r"\bguest\s+counts?\b",
    r"\bguests?\b",
    r"\bcapacity\b",
    r"\bcomplaints?\b",
    r"\bangry\b",
    r"\bunhappy\b",
    r"\bbad\b",
    r"\bcontracts?\b",
    r"\bterms?\b",
    r"\bpolic(?:y|ies)\b",
    r"\bavailability\b",
    r"\bavailable\b",
    r"\bmeet\b",
    r"\bmeeting\b",
    r"\bschedule\b",
    r"\bappointment\b",
    r"\bdate\b",
    r"\btime\b",
    r"\bbookings?\b",
    r"\breserv(?:e|ation|ed|ing)\b",
    r"\bconfirm\s+booking\b",
    r"\burgent\b",
    r"\basap\b",
    r"\bright\s+now\b",
    r"\bimmediately\b",
    r"\bemergency\b",
    r"\btoday\b",
    r"\btomorrow\b",
    r"\btonight\b",
    r"\blast[-\s]?minute\b",
)
_SMALL_TALK_LLM_ALLOW_PATTERNS = (
    r"\bmerci+\b",
    r"\bthanks?\b",
    r"\bthank\s+you\b",
    r"\bthx+\b",
    r"\bsounds?\s+good\b",
    r"\bgreat\b",
    r"\bperfect\b",
    r"\bok(?:ay)?\b",
    r"\balright\b",
    r"\bcool\b",
    r"\bsee\s+you\b",
    r"\btalk\s+soon\b",
    r"\bappreciat(?:e|ed|ing)\b",
    r"\bno\s+worries\b",
    r"\ball\s+good\b",
    r"\bhope\s+(?:you'?re|you\s+are)\s+well\b",
    r"\bhow\s+are\s+you\b",
)


@dataclass(frozen=True)
class GeneratedReply:
    suggested_text: str
    answer_supported: bool
    refusal_reason: str | None
    source_document_ids: list[str]
    rag_sources: list[dict[str, object]]
    generation_method: str
    fallback_reason: str | None = None
    small_talk_category: str | None = None


class SuggestedReplyService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.replies = SuggestedReplyRepository(session)

    async def get_tenant_suggested_reply_or_403(
        self,
        reply_id: UUID,
        ctx: TenantContext,
    ) -> SuggestedReply:
        reply = await self.replies.get(reply_id)
        if reply is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="suggested reply not found")
        if reply.tenant_id != ctx.tenant_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
        return reply

    async def update_suggested_reply(
        self,
        reply_id: UUID,
        payload: SuggestedReplyUpdate,
        ctx: TenantContext,
    ) -> SuggestedReply:
        reply = await self.get_tenant_suggested_reply_or_403(reply_id, ctx)
        update_fields = payload.model_fields_set

        text_edited = "suggested_text" in update_fields and payload.suggested_text != reply.suggested_text
        if "suggested_text" in update_fields:
            reply.suggested_text = payload.suggested_text

        # A bare text change with no explicit status means the staff member edited it.
        new_status = payload.status if "status" in update_fields else None
        if new_status is None and text_edited:
            new_status = SuggestedReplyStatus.edited

        if new_status is not None:
            reply.status = new_status
            if new_status == SuggestedReplyStatus.approved:
                reply.approved_by_user_id = ctx.user_id

        await self.session.flush()

        base_details: dict[str, object] = {
            "suggested_reply_id": reply.id,
            "conversation_id": reply.conversation_id,
            "message_id": reply.message_id,
            "answer_supported": reply.answer_supported,
            "source_document_ids": reply.source_document_ids,
            "user_id": ctx.user_id,
        }

        if new_status == SuggestedReplyStatus.approved:
            AuditLogService.record(
                self.session,
                tenant_id=ctx.tenant_id,
                actor_user_id=ctx.user_id,
                event_type=AUDIT_EVENT_SUGGESTED_REPLY_APPROVED,
                resource_type="suggested_reply",
                resource_id=reply.id,
                details=base_details,
            )
        elif new_status == SuggestedReplyStatus.rejected:
            AuditLogService.record(
                self.session,
                tenant_id=ctx.tenant_id,
                actor_user_id=ctx.user_id,
                event_type=AUDIT_EVENT_SUGGESTED_REPLY_REJECTED,
                resource_type="suggested_reply",
                resource_id=reply.id,
                details=base_details,
            )
        elif new_status == SuggestedReplyStatus.edited or text_edited:
            AuditLogService.record(
                self.session,
                tenant_id=ctx.tenant_id,
                actor_user_id=ctx.user_id,
                event_type=AUDIT_EVENT_SUGGESTED_REPLY_EDITED,
                resource_type="suggested_reply",
                resource_id=reply.id,
                details=base_details,
            )

        await self.session.commit()
        await self.session.refresh(reply)
        return reply


def _first_sentence_containing(text: str, keywords: tuple[str, ...]) -> str | None:
    for raw in re.split(r"(?<=[.!?])\s+", text.replace("\n", " ")):
        candidate = raw.strip()
        if not candidate:
            continue
        low = candidate.lower()
        if any(keyword in low for keyword in keywords):
            return candidate
    return None


def _clean_source_sentence(sentence: str) -> str:
    cleaned = re.sub(r"\s+", " ", sentence.strip())
    cleaned = re.sub(r"(?i)^(?:faq\s*:\s*)?(?:q|a)\s*:\s*", "", cleaned)
    cleaned = re.sub(r"(?i)\b(?:q|a)\s*:\s*", "", cleaned)
    cleaned = _strip_leading_document_heading(cleaned)
    return cleaned.strip()


def _strip_leading_document_heading(text: str, document_title: str | None = None) -> str:
    cleaned = text.strip()
    title = (document_title or "").strip()
    if title and cleaned.lower().startswith(title.lower()):
        cleaned = cleaned[len(title) :].lstrip(" \t\r\n:-")

    return re.sub(
        r"(?i)^(?:[a-z0-9&'/-]+\s+){0,8}"
        r"(?:deposit policy|cancellation policy|pricing packages|guest count policy|"
        r"contract terms|services faq|faq)\s+",
        "",
        cleaned,
        count=1,
    ).strip()


def _source_content_for_reply(source: dict[str, object]) -> str:
    return _strip_leading_document_heading(
        str(source.get("content", "")),
        str(source.get("document_title", "")),
    )


def _remove_source_titles_from_reply(text: str, sources: Sequence[dict[str, object]]) -> str:
    cleaned = text
    titles = sorted(
        {
            str(source.get("document_title", "")).strip()
            for source in sources
            if str(source.get("document_title", "")).strip()
        },
        key=len,
        reverse=True,
    )
    for title in titles:
        cleaned = re.sub(
            rf"(?i)\b(?:according to|based on)\s+(?:the\s+)?{re.escape(title)}\b[:,]?",
            "According to our policy,",
            cleaned,
        )
        cleaned = re.sub(rf"(?i)\b{re.escape(title)}\b[:,]?", "our policy", cleaned)
    return _normalize_reply_spacing(cleaned)


def _first_natural_source_sentence(
    text: str,
    keywords: tuple[str, ...],
    *,
    allow_questions: bool = False,
) -> str | None:
    for raw in re.split(r"(?<=[.!?])\s+", text.replace("\n", " ")):
        candidate = _clean_source_sentence(raw)
        if not candidate:
            continue
        if not allow_questions and candidate.endswith("?"):
            continue
        low = candidate.lower()
        if any(keyword in low for keyword in keywords):
            return candidate
    return None


def _first_complete_sentence(text: str) -> str | None:
    """Return the first sentence that ends with terminal punctuation.

    Used as a safe fallback instead of raw-slicing RAG content, so the generated
    reply never ends mid-sentence.
    """
    for raw in re.split(r"(?<=[.!?])\s+", text.replace("\n", " ")):
        candidate = _clean_source_sentence(raw)
        if candidate and candidate[-1] in ".!?":
            return candidate
    return None


def _pricing_summary_from_sources(content: str) -> str | None:
    packages = _extract_pricing_packages(content)
    if not packages:
        return None

    package_text = "; ".join(_format_pricing_package(package) for package in packages)
    return f"Our wedding packages are: {package_text}."


def _extract_pricing_packages(content: str) -> list[dict[str, str | None]]:
    normalized = re.sub(r"\s+", " ", content).strip()
    if not normalized:
        return []

    package_heading = re.compile(
        r"(?:^|\s)(?:\d+\.\s*)?([A-Z][A-Z\s&'/]+?PACKAGE)\s*[-:]\s*(\$\d[\d,]*(?:\.\d{2})?)",
        re.IGNORECASE,
    )
    matches = list(package_heading.finditer(normalized))
    packages: list[dict[str, str | None]] = []
    seen: set[tuple[str | None, str | None]] = set()
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(normalized)
        package_block = normalized[start:end]
        name = _title_package_name(match.group(1))
        price = match.group(2)
        key = (name.lower(), price)
        if key in seen:
            continue
        seen.add(key)
        packages.append(
            {
                "name": name,
                "price": price,
                "guest_limit": _extract_guest_limit(package_block),
            }
        )
    return packages


def _title_package_name(name: str) -> str:
    words = re.sub(r"\s+", " ", name.strip()).split(" ")
    small_words = {"and", "of", "the", "for"}
    titled = []
    for index, word in enumerate(words):
        lowered = word.lower()
        if index > 0 and lowered in small_words:
            titled.append(lowered)
        else:
            titled.append(lowered.capitalize())
    return " ".join(titled)


def _extract_guest_limit(package_block: str) -> str | None:
    patterns = (
        r"Guest count limit:\s*([^.!?;]+)",
        r"(?:accommodates|accommodate|capacity(?: is)?|up to)\s+([^.!?;]*?\d+\s+guests?)",
    )
    for pattern in patterns:
        match = re.search(pattern, package_block, flags=re.IGNORECASE)
        if not match:
            continue
        guest_limit = re.sub(r"\s+", " ", match.group(1).strip()).rstrip(".")
        if guest_limit:
            return guest_limit[0].upper() + guest_limit[1:]
    return None


def _format_pricing_package(package: dict[str, str | None]) -> str:
    name = package["name"] or "Package"
    price = package["price"] or "price available on request"
    guest_limit = package.get("guest_limit")
    if guest_limit:
        return f"{name} at {price} ({guest_limit})"
    return f"{name} at {price}"


def followup_sentence_for_intent(intent_label: str | None) -> str:
    return INTENT_FOLLOWUP_SENTENCES.get(intent_label or "", DEFAULT_FOLLOWUP_SENTENCE)


def apply_intent_followup_sentence(text: str, intent_label: str | None) -> str:
    """Ensure the draft ends with one intent-appropriate follow-up sentence."""
    desired = followup_sentence_for_intent(intent_label)
    cleaned = _remove_generic_followup_sentences(text)
    for sentence in _OLD_GENERIC_FOLLOWUP_SENTENCES:
        cleaned = _remove_sentence(cleaned, sentence)

    return _normalize_reply_spacing(f"{cleaned.rstrip()} {desired}")


def _remove_sentence(text: str, sentence: str) -> str:
    pattern = re.compile(r"(?<!\S)" + re.escape(sentence) + r"(?!\S)", re.IGNORECASE)
    return pattern.sub("", text)


def _remove_generic_followup_sentences(text: str) -> str:
    """Remove model/template next-step closings before appending one canonical line."""
    out_lines: list[str] = []
    for line in text.split("\n"):
        if not line.strip():
            out_lines.append("")
            continue
        kept = [
            sentence.strip()
            for sentence in re.split(r"(?<=[.!?])\s+", line.strip())
            if sentence.strip() and not _is_generic_followup_sentence(sentence)
        ]
        if kept:
            out_lines.append(" ".join(kept))
    return _normalize_reply_spacing("\n".join(out_lines))


def _is_generic_followup_sentence(sentence: str) -> bool:
    normalized = re.sub(r"\s+", " ", sentence.strip().strip("\"'")).lower()
    if not normalized:
        return False
    return normalized.startswith(_GENERIC_FOLLOWUP_STARTS) and any(
        marker in normalized for marker in _GENERIC_FOLLOWUP_MARKERS
    )


def _normalize_reply_spacing(text: str) -> str:
    cleaned = re.sub(r"[ \t]+", " ", text)
    cleaned = re.sub(r"\s+([.!?])", r"\1", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r" {2,}", " ", cleaned)
    return cleaned.strip()


def detect_small_talk_category(message_body: str) -> str | None:
    """Return a courtesy category only for short standalone client messages."""
    normalized = _normalize_small_talk_text(message_body)
    if not normalized:
        return None
    for category in _SMALL_TALK_ORDER:
        if normalized in _SMALL_TALK_PHRASES[category]:
            return category
    if re.fullmatch(r"hi+", normalized):
        return "greeting"
    return None


def _normalize_small_talk_text(message_body: str) -> str:
    lowered = message_body.lower().strip()
    # Treat punctuation as separators so "ok, bye" matches "ok bye", while
    # messages with business content still have extra words and do not match.
    lowered = re.sub(r"[^a-z0-9]+", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


async def _build_small_talk_reply(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    conversation_id: UUID,
    category: str,
) -> GeneratedReply:
    text = SMALL_TALK_REPLIES[category]
    if category in {"thanks", "acknowledgement"}:
        latest_outbound = await MessageRepository(session).latest_outbound_for_conversation(
            tenant_id,
            conversation_id,
        )
        if latest_outbound is not None and _outbound_confirmed_meeting(latest_outbound.body):
            text = SMALL_TALK_CONTEXTUAL_MEETING_REPLY

    return GeneratedReply(
        suggested_text=text,
        answer_supported=True,
        refusal_reason=None,
        source_document_ids=[],
        rag_sources=[],
        generation_method=_small_talk_generation_method(category),
        small_talk_category=category,
    )


def _is_safe_small_talk_llm_candidate(
    message_body: str,
    *,
    intent_label: str | None,
    risk_level: str | None,
) -> bool:
    if intent_label not in (None, "other"):
        return False
    if risk_level == "high":
        return False

    normalized = _normalize_small_talk_text(message_body)
    if not normalized:
        return False
    words = re.findall(r"[a-z0-9]+", normalized)
    if len(words) > 8 or len(message_body.strip()) > 80:
        return False
    if "?" in message_body and not re.search(r"\bhow\s+are\s+you\b", normalized):
        return False
    if not _contains_safe_small_talk_llm_marker(message_body):
        return False
    return not _contains_small_talk_llm_blocked_terms(message_body)


def _contains_small_talk_llm_blocked_terms(text: str) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in _SMALL_TALK_LLM_BLOCK_PATTERNS)


def _contains_safe_small_talk_llm_marker(text: str) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in _SMALL_TALK_LLM_ALLOW_PATTERNS)


async def _build_safe_small_talk_llm_reply(
    *,
    message_body: str,
    tenant_slug: str | None,
    llm_client_factory: Callable[[], LLMClient | None] | None = None,
) -> tuple[GeneratedReply, list[GuardrailResult]]:
    text = SMALL_TALK_LLM_GENERIC_REPLY
    fallback_reason: str | None = None
    output_events: list[GuardrailResult] = []
    llm_client = (llm_client_factory or get_llm_client)()

    if llm_client is None:
        fallback_reason = "llm_disabled_or_not_configured"
    else:
        try:
            response = await llm_client.generate_safe_small_talk_reply(
                LLMSmallTalkRequest(client_message=redact_pii(message_body))
            )
            llm_text = _clean_safe_small_talk_llm_output(response.text)
            if llm_text is None:
                fallback_reason = "small_talk_llm_invalid_response"
            else:
                output_result = check_output_guardrails(llm_text, [], tenant_slug)
                if output_result.flags:
                    output_events.append(output_result)
                if output_result.allowed:
                    text = output_result.sanitized_text or llm_text
                else:
                    fallback_reason = "small_talk_llm_output_rejected_by_guardrails"
        except Exception as exc:
            fallback_reason = f"small_talk_llm_error:{exc.__class__.__name__}"

    return (
        GeneratedReply(
            suggested_text=text,
            answer_supported=True,
            refusal_reason=None,
            source_document_ids=[],
            rag_sources=[],
            generation_method=_small_talk_generation_method(SMALL_TALK_LLM_CATEGORY),
            fallback_reason=fallback_reason,
            small_talk_category=SMALL_TALK_LLM_CATEGORY,
        ),
        output_events,
    )


def _clean_safe_small_talk_llm_output(text: str) -> str | None:
    cleaned = re.sub(r"\s+", " ", text.strip().strip("\"'")).strip()
    cleaned = re.sub(r"(?i)^reply\s*:\s*", "", cleaned).strip()
    if not cleaned:
        return None

    match = re.match(r"(.+?[.!?])(?:\s|$)", cleaned)
    if match:
        cleaned = match.group(1).strip()
    elif cleaned[-1] not in ".!?":
        cleaned = f"{cleaned}."

    if len(cleaned) > 180:
        return None
    if _contains_small_talk_llm_blocked_terms(cleaned):
        return None
    return cleaned


def _small_talk_generation_method(category: str) -> str:
    return f"{GENERATION_METHOD_SMALL_TALK_PREFIX}{category}{GENERATION_METHOD_SMALL_TALK_SUFFIX}"


def _outbound_confirmed_meeting(text: str) -> bool:
    normalized = text.lower()
    return (
        any(term in normalized for term in _MEETING_CONFIRMATION_TERMS)
        and any(term in normalized for term in _CONFIRMED_MEETING_TERMS)
    )


def _needs_escalation(message_body: str, content: str, risk_level: str | None) -> bool:
    if risk_level == "high":
        return True
    haystack = f"{message_body} {content}".lower()
    return any(keyword in haystack for keyword in _ESCALATION_KEYWORDS)


def _is_cancellation_deposit_refund_question(message_body: str, intent_label: str | None) -> bool:
    if intent_label != "cancellation_request":
        return False
    normalized = message_body.lower()
    return any(term in normalized for term in _DEPOSIT_REFUND_QUESTION_TERMS)


def _deposit_refund_summary_from_sources(content: str) -> str:
    normalized = re.sub(r"\s+", " ", content).strip()
    lowered = normalized.lower()

    booking_confirmation = re.search(
        r"\bdeposit\b[^.!?]{0,120}\bnon-refundable\b[^.!?]{0,80}\bafter booking confirmation\b",
        normalized,
        flags=re.IGNORECASE,
    ) or re.search(
        r"\bafter booking confirmation\b[^.!?]{0,120}\bdeposit\b[^.!?]{0,80}\bnon-refundable\b",
        normalized,
        flags=re.IGNORECASE,
    )
    if booking_confirmation:
        return "Our policy says the booking deposit is non-refundable after booking confirmation."

    within_refund = re.search(
        r"\bdeposit\b[^.!?]{0,120}\b("
        r"fully refundable|\d+\s*percent refundable|[a-z-]+\s+percent refundable|"
        r"partially refundable"
        r")\b[^.!?]{0,120}\bwithin\s+(?:the\s+)?(?:first\s+)?"
        r"([a-z0-9-]+)\s+(?:calendar\s+)?days\b",
        normalized,
        flags=re.IGNORECASE,
    )
    if within_refund and "non-refundable afterwards" in lowered:
        refund_amount = _format_refund_amount(within_refund.group(1))
        deadline = _format_refund_deadline(within_refund.group(2))
        return (
            f"The deposit is {refund_amount} refundable within the first {deadline} "
            "days and non-refundable afterwards."
        )

    cancel_refund = re.search(
        r"\bcancel\b[^.!?]{0,120}\bwithin\s+"
        r"([a-z0-9-]+)\s+(?:calendar\s+)?days\b[^.!?]{0,160}\breceive\s+a\s+"
        r"(full|\d+\s*percent|[a-z-]+\s+percent|partial)\s+"
        r"(?:refund\s+of\s+the\s+deposit|deposit refund)\b",
        normalized,
        flags=re.IGNORECASE,
    )
    if cancel_refund and re.search(r"\bafter\b[^.!?]{0,120}\bdeposit\b[^.!?]{0,80}\bnon-refundable\b", normalized, flags=re.IGNORECASE):
        deadline = _format_refund_deadline(cancel_refund.group(1))
        refund_amount = _format_refund_amount(cancel_refund.group(2))
        return (
            f"The deposit is {refund_amount} refundable within the first {deadline} "
            "days and non-refundable afterwards."
        )

    partial_before_event = re.search(
        r"\bdeposit\b[^.!?]{0,140}\bpartially refundable\b[^.!?]{0,160}\b"
        r"(?:more than|at least)\s+(\d+|[a-z-]+)\s+days?\s+before\b",
        normalized,
        flags=re.IGNORECASE,
    )
    if partial_before_event:
        deadline = _format_refund_deadline(partial_before_event.group(1))
        return (
            f"The deposit may be partially refundable if cancellation happens more "
            f"than {deadline} days before the event."
        )

    if "deposit" in lowered and any(term in lowered for term in ("required", "reserve", "reserves")):
        return (
            "The source confirms a deposit is required, but it does not clearly "
            "define refundability. A staff member will review the booking terms "
            "before confirming any refund."
        )

    return (
        "A staff member will review the booking terms before confirming whether "
        "the deposit is refundable."
    )


def _format_refund_amount(value: str) -> str:
    normalized = re.sub(r"\s+", " ", value.strip().lower())
    normalized = normalized.replace("-", " ")
    if normalized in {"full", "fully refundable"}:
        return "fully"
    if normalized in {"partial", "partially refundable"}:
        return "partially"
    if normalized.endswith(" refundable"):
        normalized = normalized[: -len(" refundable")].strip()
    return normalized


def _format_refund_deadline(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower().replace("-", " "))


def build_supported_reply(
    *,
    sources: list[dict[str, object]],
    message_body: str,
    risk_level: str | None,
    intent_label: str | None = None,
    guest_count_price_context: str | None = None,
) -> str:
    """Build a grounded, WhatsApp-style reply from RAG sources only.

    Every fact in the returned text traces back to ``sources``; no policy is
    invented. The wording stays concise and friendly for staff review.
    """
    primary = sources[0]
    primary_type = str(primary.get("document_type", ""))
    combined = " ".join(_source_content_for_reply(source) for source in sources[:3])
    combined_low = combined.lower()

    parts: list[str] = [GREETING]

    if guest_count_price_context is not None:
        return _guest_count_price_impact_reply(guest_count_price_context, combined)
    elif _is_cancellation_deposit_refund_question(message_body, intent_label):
        parts.append(_deposit_refund_summary_from_sources(combined))
    elif "non-refundable" in combined_low and "booking confirmation" in combined_low:
        parts.append(
            "Our policy says the booking deposit is non-refundable after "
            "booking confirmation."
        )
    elif ("partially refundable" in combined_low or "partial refund" in combined_low) and (
        "30 days" in combined_low or "thirty days" in combined_low
    ):
        parts.append(
            "Deposits may be partially refundable when "
            "cancellation happens more than 30 days before the event. The final "
            "refund depends on committed costs and manager review."
        )
    elif primary_type in ("pricing", "package"):
        sentence = _pricing_summary_from_sources(combined)
        if sentence is not None:
            parts.append(sentence)
        else:
            sentence = _first_natural_source_sentence(
                combined, ("package", "price", "pricing", "include", "cost")
            )
            if sentence is not None:
                parts.append(sentence)
            else:
                parts.append(
                    "A member of our team can confirm the exact pricing and inclusions "
                    "for your date."
                )
    elif "guest count" in combined_low:
        sentence = _first_natural_source_sentence(
            combined,
            ("guest count", "guest", "catering", "seating", "deadline"),
        )
        if sentence is not None:
            parts.append(sentence)
        else:
            parts.append(
                "Guest count changes may affect planning, catering, and seating, "
                "so our team will review the request and follow up."
            )
        parts.append(
            "Our team will review your request and follow up with you."
        )
    else:
        sentence = _first_natural_source_sentence(
            combined, tuple(word for word in message_body.lower().split() if len(word) > 3)
        )
        if sentence is None:
            # Never raw-slice RAG content (that produced mid-sentence replies);
            # fall back to the first *complete* sentence, or a safe complete line.
            sentence = (
                _first_natural_source_sentence(combined, ("policy", "the", "is"))
                or _first_complete_sentence(combined)
            )
        if sentence:
            parts.append(sentence)
        else:
            parts.append(
                "A member of our team will review your request and follow up with "
                "the details."
            )

    if _needs_escalation(message_body, combined, risk_level):
        parts.append(ESCALATION_SENTENCE)

    text = " ".join(part.strip() for part in parts if part.strip())
    return apply_intent_followup_sentence(text, intent_label)


def _compact_sources(rag_result: RagResult) -> list[dict[str, object]]:
    return [
        {
            "document_id": str(source.document_id),
            "document_title": source.document_title,
            "document_type": source.document_type,
            "content": source.content,
            "score": source.score,
        }
        for source in rag_result.sources
    ]


def _dedupe_sources_by_document(
    sources: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Collapse multiple retrieved chunks of the same document into one source.

    RAG can return several chunks from a single document, which would otherwise
    show the same ``document_id`` multiple times to the user. We keep the
    highest-scoring chunk per document and order the result by that best score
    (descending). RAG already returns sources score-descending, so this
    preserves the original ranking while leaving each document represented once.
    """
    best_by_document: dict[str, dict[str, object]] = {}
    for source in sources:
        document_id = str(source["document_id"])
        existing = best_by_document.get(document_id)
        if existing is None or float(source["score"]) > float(existing["score"]):
            best_by_document[document_id] = source
    return sorted(
        best_by_document.values(),
        key=lambda source: float(source["score"]),
        reverse=True,
    )


def generate_reply_text(
    *,
    rag_result: RagResult,
    message_body: str,
    risk_level: str | None,
    intent_label: str | None = None,
    conversation_memory: Sequence[ConversationMemoryMessage] | None = None,
    current_message_id: str | None = None,
) -> GeneratedReply:
    """Pure, deterministic generation step (no DB, no auth) for easy testing."""
    if not rag_result.answer_supported or not rag_result.sources:
        return GeneratedReply(
            suggested_text=REFUSAL_TEXT,
            answer_supported=False,
            refusal_reason=rag_result.refusal_reason or REFUSAL_REASON,
            source_document_ids=[],
            rag_sources=[],
            generation_method=GENERATION_METHOD_TEMPLATE,
        )

    compact = _compact_sources(rag_result)
    # Text is built from the full retrieved set (unchanged behavior), but the
    # sources we surface/store are deduplicated so each document appears once.
    deduped = _dedupe_sources_by_document(compact)
    source_document_ids = [str(source["document_id"]) for source in deduped]
    guest_count_price_context = _guest_count_price_followup_context(
        message_body,
        conversation_memory or (),
        current_message_id=current_message_id,
    )

    text = build_supported_reply(
        sources=compact,
        message_body=message_body,
        risk_level=risk_level,
        intent_label=intent_label,
        guest_count_price_context=guest_count_price_context,
    )
    return GeneratedReply(
        suggested_text=text,
        answer_supported=True,
        refusal_reason=None,
        source_document_ids=source_document_ids,
        rag_sources=deduped,
        generation_method=GENERATION_METHOD_TEMPLATE,
    )


def _is_payment_verification_request(message_body: str, intent_label: str | None) -> bool:
    if intent_label != "payment_issue":
        return False
    normalized = message_body.lower()
    if any(term in normalized for term in _REFUND_OR_CANCELLATION_TERMS):
        return False
    return any(term in normalized for term in _PAYMENT_VERIFICATION_TERMS)


def _is_contact_followup_request(message_body: str) -> bool:
    return any(pattern.search(message_body) for pattern in _CONTACT_FOLLOWUP_PATTERNS)


def _is_guest_count_operational_request(message_body: str, intent_label: str | None) -> bool:
    if intent_label == "guest_count_change":
        return True
    return any(pattern.search(message_body) for pattern in _GUEST_COUNT_OPERATIONAL_PATTERNS)


def _guest_count_review_reply(message_body: str) -> str:
    count = _guest_count_phrase(message_body)
    if count is not None:
        context = f"Since this involves adding {count}, "
    else:
        context = "Since this involves a guest-count or capacity change, "
    return (
        f"Hi, thank you for letting us know. {context}"
        "our team will need to review venue capacity, catering availability, "
        "seating arrangements, and any package or price impact. We'll follow up "
        "with you shortly."
    )


def _guest_count_price_impact_reply(context: str, source_content: str) -> str:
    change = _guest_count_change_details(context)
    if change is None:
        return (
            "Yes, this guest-count change may affect the final invoice. Since the "
            "updated count may affect package capacity, catering, setup, and "
            "staffing, our team will review your booking details and confirm the "
            "updated invoice before final approval."
        )

    package = _supported_package_for_guest_count(source_content, change[1])
    if package is not None:
        return (
            f"Yes, changing the guest count from {change[0]} to {change[1]} may "
            f"affect the final invoice. Since the {package} supports up to "
            f"{change[1]} guests, our team will review your booking details and "
            "confirm the updated package, capacity, and final invoice before "
            "approval."
        )

    return (
        f"Yes, changing the guest count from {change[0]} to {change[1]} will "
        "likely affect the price or final invoice. Since "
        f"{change[1]} guests may affect package capacity, catering, setup, and "
        "staffing, our team will review your booking details and confirm the "
        "updated invoice before final approval."
    )


def _guest_count_change_details(context: str) -> tuple[int, int] | None:
    match = re.search(r"\bfrom\s+(\d+)\s+to\s+(\d+)\s+guests?\b", context, flags=re.IGNORECASE)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def _supported_package_for_guest_count(source_content: str, updated_count: int) -> str | None:
    normalized = re.sub(r"\s+", " ", source_content)
    pattern = re.compile(
        r"\b((?:[A-Z][A-Za-z0-9'&-]*\s+){0,5}Package)\b"
        r"[^.!?]{0,140}?\b(?:accommodates|supports|capacity(?:\s+is)?|up\s+to)\s+"
        r"(?:up\s+to\s+)?(\d+)\s+guests?\b",
        re.IGNORECASE,
    )
    for match in pattern.finditer(normalized):
        capacity = int(match.group(2))
        if capacity == updated_count:
            return _clean_package_name(match.group(1))
    return None


def _clean_package_name(value: str) -> str:
    words = re.sub(r"\s+", " ", value.strip()).split(" ")
    if words and words[0].lower() == "the":
        words = words[1:]
    return " ".join(word[:1].upper() + word[1:] for word in words)


def _is_guest_count_price_impact_text(text: str) -> bool:
    lowered = text.lower()
    return (
        "changing the guest count from" in lowered
        and (
            ("updated invoice" in lowered and "before final approval" in lowered)
            or "final invoice before approval" in lowered
        )
    )


def _guest_count_phrase(message_body: str) -> str | None:
    patterns = (
        r"\b(\d+\s+extra\s+guests?)\b",
        r"\b(\d+\s+additional\s+guests?)\b",
        r"\b(\d+\s+more\s+guests?)\b",
        r"\b(\d+\s+guests?)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, message_body, flags=re.IGNORECASE)
        if match:
            return match.group(1).lower()
    return None


def _is_high_risk_review_request(
    message_body: str,
    intent_label: str | None,
    risk_level: str | None,
) -> bool:
    normalized = message_body.lower()
    has_complaint = intent_label == "complaint" or any(term in normalized for term in _COMPLAINT_TERMS)
    has_handoff = intent_label == "human_escalation" or any(
        term in normalized for term in _HUMAN_ESCALATION_TERMS
    )
    return has_complaint or has_handoff


def _high_risk_review_reply(
    message_body: str,
    intent_label: str | None,
    risk_level: str | None,
) -> str:
    issue = _issue_category(message_body)
    urgency = _urgency_phrase(message_body)
    wants_manager = intent_label == "human_escalation" or any(
        term in message_body.lower() for term in _HUMAN_ESCALATION_TERMS
    )

    parts = ["I'm sorry to hear this, and I understand this needs careful attention."]
    if urgency is not None:
        parts.append(f"I understand this is urgent with {urgency}.")
    if issue is not None:
        parts.append(f"I'll flag this for manager review so the {issue} can be checked as soon as possible.")
    elif wants_manager or risk_level == "high":
        parts.append("I'll flag this for manager review so the team can look into it as soon as possible.")
    else:
        parts.append("Our team will review the details and follow up with you shortly.")
    if wants_manager:
        parts.append("A manager or team member will follow up with you shortly.")
    else:
        parts.append("A team member will follow up with you shortly.")
    return " ".join(parts)


def _issue_category(message_body: str) -> str | None:
    normalized = message_body.lower()
    if any(term in normalized for term in ("decoration", "decor", "floral", "flowers", "styling")):
        return "decoration issue"
    if any(term in normalized for term in ("payment", "deposit", "invoice", "receipt")):
        return "payment issue"
    if any(term in normalized for term in ("guest count", "extra guests", "additional guests", "more guests")):
        return "guest-count request"
    if any(term in normalized for term in ("catering", "menu", "food")):
        return "catering issue"
    if any(term in normalized for term in ("venue", "seating", "layout")):
        return "venue or seating issue"
    if any(term in normalized for term in ("cancel", "cancellation", "refund")):
        return "cancellation or refund request"
    return None


def _urgency_phrase(message_body: str) -> str | None:
    normalized = message_body.lower()
    if "next week" in normalized:
        return "the wedding coming up next week"
    if "this week" in normalized:
        return "the wedding coming up this week"
    if "tomorrow" in normalized:
        return "the wedding coming up tomorrow"
    if "today" in normalized:
        return "the wedding coming up today"
    if any(term in normalized for term in ("immediately", "urgent", "asap")):
        return "the urgent timing"
    return None


async def _generate_calendar_availability_reply(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    user_id: UUID | None,
    message: Message,
    message_body: str,
) -> GeneratedReply:
    parsed = parse_availability_request(
        message_body,
        reference_time=message.sent_at,
    )
    if not parsed.has_exact_time:
        return GeneratedReply(
            suggested_text=_no_exact_time_availability_reply(message_body),
            answer_supported=False,
            refusal_reason=AVAILABILITY_PARSE_REFUSAL_REASON,
            source_document_ids=[],
            rag_sources=[],
            generation_method=GENERATION_METHOD_CALENDAR_AVAILABILITY,
        )

    assert parsed.start_time is not None
    assert parsed.end_time is not None
    try:
        availability = await CalendarService(session).check_tenant_availability(
            start_time=parsed.start_time,
            end_time=parsed.end_time,
            timezone_name=parsed.timezone,
            tenant_id=tenant_id,
            actor_user_id=user_id,
            commit=False,
        )
    except Exception:
        return GeneratedReply(
            suggested_text=(
                "Hi, thank you for your message. A staff member will check our "
                "calendar availability manually and follow up with you."
            ),
            answer_supported=False,
            refusal_reason=AVAILABILITY_MANUAL_REVIEW_REASON,
            source_document_ids=[],
            rag_sources=[],
            generation_method=GENERATION_METHOD_CALENDAR_AVAILABILITY,
        )

    requested_time = _format_requested_slot(parsed.start_time, parsed.end_time)
    if availability.reason == "calendar_not_connected":
        return GeneratedReply(
            suggested_text=(
                f"Hi, thank you for your message. We'll check availability for "
                f"{requested_time} manually and follow up with you."
            ),
            answer_supported=False,
            refusal_reason=AVAILABILITY_MANUAL_REVIEW_REASON,
            source_document_ids=[],
            rag_sources=[],
            generation_method=GENERATION_METHOD_CALENDAR_AVAILABILITY,
        )

    if availability.available is True:
        meeting_purpose = _meeting_purpose_sentence(message_body)
        text = (
            f"Hi, thank you for your message. {requested_time} works for us. "
            f"We can schedule the meeting then{meeting_purpose}"
        )
    else:
        if availability.alternatives:
            options = _format_alternative_slots(
                _format_requested_slot(slot.start_time, slot.end_time)
                for slot in availability.alternatives
            )
            text = (
                f"Hi, thank you for your message. {requested_time} is not available, "
                f"but we can offer {options} instead. Please let us know which "
                "time works best for you."
            )
        else:
            text = (
                f"Hi, thank you for your message. {requested_time} is not available. "
                "Could you share another preferred time that works for you?"
            )

    return GeneratedReply(
        suggested_text=text,
        answer_supported=True,
        refusal_reason=None,
        source_document_ids=[],
        rag_sources=[],
        generation_method=GENERATION_METHOD_CALENDAR_AVAILABILITY,
    )


def _no_exact_time_availability_reply(message_body: str) -> str:
    date_phrase = _availability_date_phrase(message_body)
    if _explicit_meeting_request(message_body):
        if date_phrase:
            return (
                f"{GREETING} We can check meeting availability for {date_phrase}. "
                "Could you share your preferred time?"
            )
        return (
            f"{GREETING} Could you share your preferred date and time for the "
            "meeting? We'll check availability and follow up with you."
        )

    event_type = _event_type_phrase(message_body)
    detail_prompt = _missing_event_detail_prompt(message_body, event_type)
    if date_phrase:
        target = _event_availability_target(event_type, date_phrase)
        return f"{GREETING} We'll check availability for {target}. Could you share {detail_prompt}?"

    return f"{GREETING} Could you share your event date, {detail_prompt}?"


def _availability_date_phrase(message_body: str) -> str | None:
    for pattern in (
        _MONTH_DATE_PATTERN,
        _DAY_MONTH_DATE_PATTERN,
        _NUMERIC_DATE_PATTERN,
    ):
        match = pattern.search(message_body)
        if match:
            return _clean_date_phrase(match.group(0))

    relative_match = _RELATIVE_DATE_PATTERN.search(message_body)
    if relative_match:
        return _clean_date_phrase(relative_match.group(0))

    return None


def _clean_date_phrase(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" ,.!?")


def _explicit_meeting_request(message_body: str) -> bool:
    normalized = message_body.lower()
    return bool(
        re.search(r"\b(?:meeting|call|appointment)\b", normalized)
        or re.search(r"\bmeet\b", normalized)
    )


def _event_type_phrase(message_body: str) -> str | None:
    normalized = message_body.lower()
    for term, label in _EVENT_TYPE_TERMS:
        if re.search(rf"\b{re.escape(term)}\b", normalized):
            return label
    return None


def _event_availability_target(event_type: str | None, date_phrase: str) -> str:
    target = f"your {event_type}" if event_type else "your event"
    if _date_phrase_reads_with_on(date_phrase):
        return f"{target} on {date_phrase}"
    return f"{target} {date_phrase}"


def _date_phrase_reads_with_on(date_phrase: str) -> bool:
    normalized = date_phrase.lower()
    explicit_date = (
        _MONTH_DATE_PATTERN.fullmatch(date_phrase)
        or _DAY_MONTH_DATE_PATTERN.fullmatch(date_phrase)
        or _NUMERIC_DATE_PATTERN.fullmatch(date_phrase)
    )
    return bool(explicit_date) or normalized in {
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
    }


def _missing_event_detail_prompt(message_body: str, event_type: str | None) -> str:
    normalized = message_body.lower()
    missing: list[str] = []
    guest_count_pattern = (
        r"\b(?:about|around|approx(?:imately)?|for)?\s*"
        r"\d+\s*(?:guests?|people|pax)\b"
    )
    if not re.search(guest_count_pattern, normalized):
        missing.append("guest count")
    if not re.search(r"\b(?:venue|location|address)\b", normalized):
        missing.append("venue/location")
    if not re.search(r"\b(?:package|classic|premium|luxury|gold|silver)\b", normalized):
        missing.append("package preference")
    if event_type is None:
        missing.append("event type")
    if not missing:
        return "any other event details"
    return _format_natural_list(missing)


def _format_natural_list(items: Sequence[str]) -> str:
    item_list = list(items)
    if len(item_list) <= 1:
        return item_list[0] if item_list else "details"
    if len(item_list) == 2:
        return f"{item_list[0]} and {item_list[1]}"
    return f"{', '.join(item_list[:-1])}, and {item_list[-1]}"


def _format_requested_slot(start_time, end_time) -> str:
    start_day = start_time.strftime("%A, %B ") + str(start_time.day)
    return f"{start_day} at {_format_time(start_time)}"


def _format_alternative_slots(slots) -> str:
    slot_list = list(slots)
    if len(slot_list) <= 1:
        return slot_list[0] if slot_list else "another time"
    return f"{', '.join(slot_list[:-1])} or {slot_list[-1]}"


def _meeting_purpose_sentence(message_body: str) -> str:
    match = re.search(r"\bto\s+([^?.!]+)", message_body, flags=re.IGNORECASE)
    if not match:
        return "."
    purpose = re.sub(r"\s+", " ", match.group(1)).strip()
    if not purpose:
        return "."
    return f" to {purpose}."


def _format_time(value) -> str:
    hour = value.hour % 12 or 12
    suffix = "AM" if value.hour < 12 else "PM"
    if value.minute:
        return f"{hour}:{value.minute:02d} {suffix}"
    return f"{hour} {suffix}"


def build_contextual_rag_query(
    message_body: str,
    memory_messages: Sequence[ConversationMemoryMessage],
    *,
    current_message_id: str | None = None,
) -> str:
    """Resolve small follow-up references for retrieval only.

    The returned text is used as the RAG query; the raw client message remains
    the message shown to staff and passed to the reply generator. Memory is
    already tenant- and conversation-scoped by ``ConversationMemoryService``.
    """
    message_body = message_body.strip()
    if not message_body or not _FOLLOWUP_REFERENCE_PATTERN.search(message_body):
        return message_body

    antecedent = _latest_prior_inbound_memory(
        memory_messages,
        current_message_id=current_message_id,
    )
    if antecedent is None:
        return message_body

    phrase = _antecedent_phrase(antecedent.body)
    if (
        phrase is not None
        and _PRICE_OR_INVOICE_PATTERN.search(message_body)
        and _guest_count_change_context(antecedent.body) is not None
    ):
        return (
            f"{_rewrite_followup_reference(message_body, phrase, antecedent.body)} "
            "guest count pricing invoice FAQ capacity package"
        )
    if phrase is None:
        return f"{message_body} Previous client message: {antecedent.body.strip()}"

    return _rewrite_followup_reference(message_body, phrase, antecedent.body)


def _rewrite_followup_reference(message_body: str, phrase: str, antecedent_body: str) -> str:
    rewritten = message_body
    for pattern in _REFERENCE_REPLACEMENTS:
        next_value = pattern.sub(phrase, rewritten, count=1)
        if next_value != rewritten:
            return next_value
        rewritten = next_value
    return f"{message_body} Previous client message: {antecedent_body.strip()}"


def _latest_prior_inbound_memory(
    memory_messages: Sequence[ConversationMemoryMessage],
    *,
    current_message_id: str | None,
) -> ConversationMemoryMessage | None:
    for item in reversed(memory_messages):
        if item.direction != "inbound":
            continue
        if current_message_id is not None and item.message_id == current_message_id:
            continue
        body = item.body.strip()
        if not body or _FOLLOWUP_REFERENCE_PATTERN.fullmatch(body):
            continue
        return item
    return None


def _antecedent_phrase(text: str) -> str | None:
    cleaned = re.sub(r"\s+", " ", text.strip()).rstrip("?.!")
    if not cleaned:
        return None

    guest_count_context = _guest_count_change_context(cleaned)
    if guest_count_context is not None:
        return f"the guest count {guest_count_context}"

    add_patterns = (
        r"^(?:can|could|may|would)\s+(?:we|i)\s+add\s+(.+)$",
        r"^is\s+it\s+possible\s+to\s+add\s+(.+)$",
        r"^(?:we|i)\s+(?:want|would\s+like|need)\s+to\s+add\s+(.+)$",
        r"^add\s+(.+)$",
    )
    for pattern in add_patterns:
        match = re.match(pattern, cleaned, flags=re.IGNORECASE)
        if match:
            return f"adding {match.group(1).strip()}"

    return None


def _guest_count_change_context(text: str) -> str | None:
    for pattern in (_GUEST_COUNT_CHANGE_PATTERN, _GUEST_COUNT_FROM_TO_PATTERN):
        match = pattern.search(text)
        if not match:
            continue
        old_count = match.group(1)
        new_count = match.group(2)
        if old_count == new_count:
            return f"from {old_count} to {new_count} guests"
        direction = "increased" if int(new_count) > int(old_count) else "changed"
        return f"{direction} from {old_count} to {new_count} guests"
    return None


def _guest_count_price_followup_context(
    message_body: str,
    memory_messages: Sequence[ConversationMemoryMessage],
    *,
    current_message_id: str | None,
) -> str | None:
    if not _FOLLOWUP_REFERENCE_PATTERN.search(message_body):
        return None
    if not _PRICE_OR_INVOICE_PATTERN.search(message_body):
        return None
    antecedent = _latest_prior_inbound_memory(
        memory_messages,
        current_message_id=current_message_id,
    )
    if antecedent is None:
        return None
    return _guest_count_change_context(antecedent.body)


async def generate_reply_text_with_optional_llm(
    *,
    rag_result: RagResult,
    message_body: str,
    intent_label: str | None,
    risk_level: str | None,
    risk_reason: str | None,
    tenant_slug: str | None,
    current_message_id: str | None = None,
    memory_messages: Sequence[ConversationMemoryMessage] | None = None,
    conversation_memory: list[dict[str, str]] | None = None,
    llm_client_factory: Callable[[], LLMClient | None] | None = None,
) -> GeneratedReply:
    template_reply = generate_reply_text(
        rag_result=rag_result,
        message_body=message_body,
        risk_level=risk_level,
        intent_label=intent_label,
        conversation_memory=memory_messages,
        current_message_id=current_message_id,
    )
    if not template_reply.answer_supported or not template_reply.rag_sources:
        return template_reply
    if _is_guest_count_price_impact_text(template_reply.suggested_text):
        return template_reply

    llm_client = (llm_client_factory or get_llm_client)()
    if llm_client is None:
        return _with_fallback_reason(template_reply, "llm_disabled_or_not_configured")

    retrieval_result = check_retrieval_guardrails(template_reply.rag_sources, tenant_slug)
    if not retrieval_result.result.allowed:
        return _with_fallback_reason(template_reply, "llm_retrieval_rejected_by_guardrails")
    prompt_sources = retrieval_result.sources
    prompt_memory = [
        {
            **message,
            "body": redact_pii(str(message.get("body", ""))),
        }
        for message in (conversation_memory or [])
    ]

    try:
        response = await llm_client.generate_suggested_reply(
            LLMReplyRequest(
                client_message=redact_pii(message_body),
                intent_label=intent_label,
                risk_level=risk_level,
                risk_reason=redact_pii(risk_reason or "") or None,
                rag_sources=prompt_sources,
                conversation_memory=prompt_memory,
            )
        )
        llm_text = response.text.strip()
        if not llm_text:
            raise ValueError("llm_empty_response")
        llm_text = apply_intent_followup_sentence(llm_text, intent_label)
        llm_text = _remove_source_titles_from_reply(llm_text, template_reply.rag_sources)
        output_result = check_output_guardrails(
            llm_text,
            template_reply.rag_sources,
            tenant_slug,
        )
        if not output_result.allowed:
            return _with_fallback_reason(template_reply, "llm_output_rejected_by_guardrails")
        return GeneratedReply(
            suggested_text=output_result.sanitized_text or llm_text,
            answer_supported=True,
            refusal_reason=None,
            source_document_ids=template_reply.source_document_ids,
            rag_sources=template_reply.rag_sources,
            generation_method=GENERATION_METHOD_LLM,
        )
    except Exception as exc:
        return _with_fallback_reason(template_reply, f"llm_error:{exc.__class__.__name__}")


def _with_fallback_reason(reply: GeneratedReply, reason: str) -> GeneratedReply:
    return GeneratedReply(
        suggested_text=reply.suggested_text,
        answer_supported=reply.answer_supported,
        refusal_reason=reply.refusal_reason,
        source_document_ids=reply.source_document_ids,
        rag_sources=reply.rag_sources,
        generation_method=reply.generation_method,
        fallback_reason=reason,
        small_talk_category=reply.small_talk_category,
    )


async def generate_suggested_reply(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    user_id: UUID | None,
    conversation: Conversation,
    message: Message,
    llm_client_factory: Callable[[], LLMClient | None] | None = None,
) -> SuggestedReply:
    """Generate, persist, and audit a suggested reply for ``message``.

    The caller is responsible for tenant-ownership checks on ``conversation``
    and ``message``. RAG retrieval is always scoped to ``tenant_id`` so a reply
    can only ever cite the current tenant's documents.
    """
    tenant_slug = await TenantRepository(session).get_slug(tenant_id)
    guardrail_events: list[tuple[str, GuardrailResult]] = []
    memory_messages = []
    rag_query_audit: str | None = None

    input_result = check_input_guardrails(message.body, tenant_slug)
    if input_result.flags:
        guardrail_events.append(("input", input_result))

    message_body = input_result.sanitized_text or message.body
    small_talk_category = detect_small_talk_category(message_body)

    if not input_result.allowed:
        generated = GeneratedReply(
            suggested_text=SAFE_REFUSAL,
            answer_supported=False,
            refusal_reason=input_result.reason or SAFE_REFUSAL,
            source_document_ids=[],
            rag_sources=[],
            generation_method=GENERATION_METHOD_TEMPLATE,
        )
    elif small_talk_category is not None:
        generated = await _build_small_talk_reply(
            session,
            tenant_id=tenant_id,
            conversation_id=conversation.id,
            category=small_talk_category,
        )
    elif _is_safe_small_talk_llm_candidate(
        message_body,
        intent_label=message.intent_label,
        risk_level=message.risk_level,
    ):
        generated, output_events = await _build_safe_small_talk_llm_reply(
            message_body=message_body,
            tenant_slug=tenant_slug,
            llm_client_factory=llm_client_factory,
        )
        guardrail_events.extend(("output", event) for event in output_events)
    elif _is_payment_verification_request(
        message_body,
        message.intent_label,
    ):
        generated = GeneratedReply(
            suggested_text=PAYMENT_VERIFICATION_REPLY,
            answer_supported=False,
            refusal_reason=PAYMENT_VERIFICATION_REFUSAL_REASON,
            source_document_ids=[],
            rag_sources=[],
            generation_method=GENERATION_METHOD_TEMPLATE,
        )
    elif is_availability_question(message_body, message.intent_label):
        generated = await _generate_calendar_availability_reply(
            session,
            tenant_id=tenant_id,
            user_id=user_id,
            message=message,
            message_body=message_body,
        )
    elif _is_contact_followup_request(message_body):
        generated = GeneratedReply(
            suggested_text=CONTACT_FOLLOWUP_REPLY,
            answer_supported=False,
            refusal_reason=CONTACT_FOLLOWUP_REFUSAL_REASON,
            source_document_ids=[],
            rag_sources=[],
            generation_method=GENERATION_METHOD_TEMPLATE,
        )
    else:
        memory_messages = await ConversationMemoryService().load_recent(
            tenant_id=tenant_id,
            conversation_id=conversation.id,
        )
        rag_query = build_contextual_rag_query(
            message_body,
            memory_messages,
            current_message_id=str(message.id),
        )
        rag_result = await retrieve(
            session,
            query=rag_query,
            tenant_id=tenant_id,
            top_k=5,
            actor_user_id=user_id,
            audit=False,
            enforce_guardrails=False,
        )
        rag_query_audit = rag_result.query
        generated = await generate_reply_text_with_optional_llm(
            rag_result=rag_result,
            message_body=message_body,
            intent_label=message.intent_label,
            risk_level=message.risk_level,
            risk_reason=message.risk_reason,
            tenant_slug=tenant_slug,
            current_message_id=str(message.id),
            memory_messages=memory_messages,
            conversation_memory=[
                {
                    "message_id": item.message_id,
                    "direction": item.direction,
                    "body": item.body,
                    "sent_at": item.sent_at,
                }
                for item in memory_messages
            ],
            llm_client_factory=llm_client_factory,
        )
        if (
            not generated.answer_supported
            and not generated.rag_sources
            and _is_guest_count_operational_request(message_body, message.intent_label)
        ):
            generated = GeneratedReply(
                suggested_text=apply_intent_followup_sentence(
                    _guest_count_review_reply(message_body),
                    message.intent_label,
                ),
                answer_supported=False,
                refusal_reason=GUEST_COUNT_REVIEW_REFUSAL_REASON,
                source_document_ids=[],
                rag_sources=[],
                generation_method=GENERATION_METHOD_TEMPLATE,
            )
        elif (
            not generated.answer_supported
            and not generated.rag_sources
            and _is_high_risk_review_request(
                message_body,
                message.intent_label,
                message.risk_level,
            )
        ):
            generated = GeneratedReply(
                suggested_text=apply_intent_followup_sentence(
                    _high_risk_review_reply(
                        message_body,
                        message.intent_label,
                        message.risk_level,
                    ),
                    message.intent_label,
                ),
                answer_supported=False,
                refusal_reason=HIGH_RISK_REVIEW_REFUSAL_REASON,
                source_document_ids=[],
                rag_sources=[],
                generation_method=GENERATION_METHOD_TEMPLATE,
            )
        (
            suggested_text,
            rag_sources,
            answer_supported,
            refusal_reason,
            output_events,
        ) = apply_guardrails_to_suggested_reply(
            suggested_text=generated.suggested_text,
            rag_sources=generated.rag_sources,
            answer_supported=generated.answer_supported,
            refusal_reason=generated.refusal_reason,
            tenant_slug=tenant_slug,
        )
        guardrail_events.extend(("retrieval" if event.flags and any(flag.startswith("pii_in_retrieved") or flag.startswith("suspicious_retrieved") or flag.startswith("cross_tenant_context") for flag in event.flags) else "output", event) for event in output_events)
        generated = GeneratedReply(
            suggested_text=suggested_text,
            answer_supported=answer_supported,
            refusal_reason=refusal_reason,
            source_document_ids=[
                str(source["document_id"])
                for source in rag_sources
                if str(source["document_id"]) in generated.source_document_ids
            ],
            rag_sources=rag_sources,
            generation_method=generated.generation_method,
            fallback_reason=generated.fallback_reason,
        )

    reply = SuggestedReply(
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        message_id=message.id,
        suggested_text=generated.suggested_text,
        status=SuggestedReplyStatus.draft,
        source_document_ids=generated.source_document_ids,
        rag_sources=generated.rag_sources,
        answer_supported=generated.answer_supported,
        refusal_reason=generated.refusal_reason,
        generation_method=generated.generation_method,
        created_by_user_id=user_id,
    )
    await SuggestedReplyRepository(session).add(reply)

    for rail_type, event in guardrail_events:
        audit_guardrail_event(
            session,
            tenant_id=tenant_id,
            actor_user_id=user_id,
            rail_type=rail_type,
            result=event,
            resource_type="suggested_reply",
            resource_id=reply.id,
            conversation_id=conversation.id,
            message_id=message.id,
            suggested_reply_id=reply.id,
            original_text=message.body if rail_type == "input" else generated.suggested_text,
        )

    source_titles = [str(source.get("document_title")) for source in generated.rag_sources]
    details: dict[str, object] = {
        "suggested_reply_id": reply.id,
        "conversation_id": conversation.id,
        "message_id": message.id,
        "answer_supported": generated.answer_supported,
        "generation_method": generated.generation_method,
        "llm_fallback_reason": generated.fallback_reason,
        "memory_message_count": len(memory_messages),
        "rag_query": rag_query_audit,
        "reply_strategy": (
            "small_talk_llm"
            if generated.small_talk_category == SMALL_TALK_LLM_CATEGORY
            else None
        ),
        "small_talk_category": generated.small_talk_category,
        "source_document_ids": generated.source_document_ids,
        "source_document_titles": source_titles,
        "user_id": user_id,
    }
    if generated.answer_supported:
        AuditLogService.record(
            session,
            tenant_id=tenant_id,
            actor_user_id=user_id,
            event_type=AUDIT_EVENT_SUGGESTED_REPLY_GENERATED,
            resource_type="suggested_reply",
            resource_id=reply.id,
            details=details,
        )
    else:
        AuditLogService.record(
            session,
            tenant_id=tenant_id,
            actor_user_id=user_id,
            event_type=AUDIT_EVENT_SUGGESTED_REPLY_REFUSED_NO_SOURCE,
            resource_type="suggested_reply",
            resource_id=reply.id,
            details={**details, "refusal_reason": generated.refusal_reason},
        )

    await session.commit()
    await session.refresh(reply)
    return reply
