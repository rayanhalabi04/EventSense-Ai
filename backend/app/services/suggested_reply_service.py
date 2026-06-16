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
from app.repositories.suggested_reply_repository import SuggestedReplyRepository
from app.repositories.tenant_repository import TenantRepository
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
from app.services.llm_service import LLMClient, LLMReplyRequest, get_llm_client
from app.schemas.suggested_reply import SuggestedReplyUpdate
from app.services.conversation_memory_service import (
    ConversationMemoryMessage,
    ConversationMemoryService,
)
from app.services.rag_service import RagResult, retrieve


GENERATION_METHOD_TEMPLATE = "template_v1"
GENERATION_METHOD_LLM = "llm_v1"

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
PAYMENT_VERIFICATION_REPLY = (
    "Hi, thank you for your message. We'll ask our team to verify your "
    "deposit/payment confirmation and update you shortly."
)
PAYMENT_VERIFICATION_REFUSAL_REASON = "Payment confirmation requires staff verification."
CONTACT_FOLLOWUP_REPLY = (
    "Thank you. I'll ask a team member to contact you about your booking."
)
CONTACT_FOLLOWUP_REFUSAL_REASON = "Contact requests require staff follow-up."
GUEST_COUNT_REVIEW_REFUSAL_REASON = "Guest count/capacity changes require staff review."
HIGH_RISK_REVIEW_REFUSAL_REASON = "High-risk complaint or human escalation requires staff review."

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

_FOLLOWUP_REFERENCE_PATTERN = re.compile(
    r"\b(that|this|it)\b|\bthe\s+change\b|\bchange\s+the\s+price\b",
    re.IGNORECASE,
)
_REFERENCE_REPLACEMENTS = (
    re.compile(r"\bthe\s+change\b", re.IGNORECASE),
    re.compile(r"\b(that|this|it)\b", re.IGNORECASE),
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
@dataclass(frozen=True)
class GeneratedReply:
    suggested_text: str
    answer_supported: bool
    refusal_reason: str | None
    source_document_ids: list[str]
    rag_sources: list[dict[str, object]]
    generation_method: str
    fallback_reason: str | None = None


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
    return cleaned.strip()


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


def _needs_escalation(message_body: str, content: str, risk_level: str | None) -> bool:
    if risk_level == "high":
        return True
    haystack = f"{message_body} {content}".lower()
    return any(keyword in haystack for keyword in _ESCALATION_KEYWORDS)


def build_supported_reply(
    *,
    sources: list[dict[str, object]],
    message_body: str,
    risk_level: str | None,
) -> str:
    """Build a grounded, WhatsApp-style reply from RAG sources only.

    Every fact in the returned text traces back to ``sources``; no policy is
    invented. The wording stays concise and friendly for staff review.
    """
    primary = sources[0]
    primary_type = str(primary.get("document_type", ""))
    combined = " ".join(str(source.get("content", "")) for source in sources[:3])
    combined_low = combined.lower()

    parts: list[str] = [GREETING]

    if "non-refundable" in combined_low and "booking confirmation" in combined_low:
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
    elif primary_type in ("pricing", "package"):
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

    return " ".join(part.strip() for part in parts if part.strip())


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

    text = build_supported_reply(
        sources=compact,
        message_body=message_body,
        risk_level=risk_level,
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
    if phrase is None:
        return f"{message_body} Previous client message: {antecedent.body.strip()}"

    rewritten = message_body
    for pattern in _REFERENCE_REPLACEMENTS:
        rewritten = pattern.sub(phrase, rewritten, count=1)
        if rewritten != message_body:
            return rewritten
    return f"{message_body} Previous client message: {antecedent.body.strip()}"


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


async def generate_reply_text_with_optional_llm(
    *,
    rag_result: RagResult,
    message_body: str,
    intent_label: str | None,
    risk_level: str | None,
    risk_reason: str | None,
    tenant_slug: str | None,
    conversation_memory: list[dict[str, str]] | None = None,
    llm_client_factory: Callable[[], LLMClient | None] | None = None,
) -> GeneratedReply:
    template_reply = generate_reply_text(
        rag_result=rag_result,
        message_body=message_body,
        risk_level=risk_level,
    )
    if not template_reply.answer_supported or not template_reply.rag_sources:
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

    if not input_result.allowed:
        generated = GeneratedReply(
            suggested_text=SAFE_REFUSAL,
            answer_supported=False,
            refusal_reason=input_result.reason or SAFE_REFUSAL,
            source_document_ids=[],
            rag_sources=[],
            generation_method=GENERATION_METHOD_TEMPLATE,
        )
    elif _is_payment_verification_request(
        input_result.sanitized_text or message.body,
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
    elif _is_contact_followup_request(input_result.sanitized_text or message.body):
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
        message_body = input_result.sanitized_text or message.body
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
                suggested_text=_guest_count_review_reply(message_body),
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
                suggested_text=_high_risk_review_reply(
                    message_body,
                    message.intent_label,
                    message.risk_level,
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
