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
from typing import Callable
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
)
from app.services.llm_service import LLMClient, LLMReplyRequest, get_llm_client
from app.schemas.suggested_reply import SuggestedReplyUpdate
from app.services.conversation_memory_service import ConversationMemoryService
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
    primary_title = str(primary.get("document_title", "company documents"))
    primary_type = str(primary.get("document_type", ""))
    combined = " ".join(str(source.get("content", "")) for source in sources[:3])
    combined_low = combined.lower()

    parts: list[str] = [GREETING]

    if "non-refundable" in combined_low and "booking confirmation" in combined_low:
        parts.append(
            "According to our policy, the booking deposit is non-refundable after "
            "booking confirmation."
        )
    elif ("partially refundable" in combined_low or "partial refund" in combined_low) and (
        "30 days" in combined_low or "thirty days" in combined_low
    ):
        parts.append(
            "According to our policy, deposits may be partially refundable when "
            "cancellation happens more than 30 days before the event. The final "
            "refund depends on committed costs and manager review."
        )
    elif "guest count" in combined_low:
        sentence = _first_sentence_containing(combined, ("guest count",))
        if sentence is not None:
            parts.append(f"According to our {primary_title}: {sentence}")
        else:
            parts.append(
                f"According to our {primary_title}, there is a guest count "
                "confirmation deadline; please confirm with us before it passes."
            )
        parts.append(
            "If the deadline has already passed, I can ask a manager to review "
            "your options."
        )
    elif primary_type in ("pricing", "package"):
        sentence = _first_sentence_containing(
            combined, ("package", "price", "pricing", "include", "cost")
        )
        if sentence is not None:
            parts.append(f"Based on our {primary_title}: {sentence}")
        else:
            parts.append(
                f"I can share details from our {primary_title}; a member of our "
                "team will confirm the exact pricing and inclusions for your date."
            )
    else:
        sentence = _first_sentence_containing(
            combined, tuple(word for word in message_body.lower().split() if len(word) > 3)
        )
        if sentence is None:
            sentence = _first_sentence_containing(combined, ("policy", "the", "is")) or combined[:240]
        parts.append(f"According to our {primary_title}: {sentence}")

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

    try:
        response = await llm_client.generate_suggested_reply(
            LLMReplyRequest(
                client_message=message_body,
                intent_label=intent_label,
                risk_level=risk_level,
                risk_reason=risk_reason,
                rag_sources=template_reply.rag_sources,
                conversation_memory=conversation_memory or [],
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
    else:
        rag_result = await retrieve(
            session,
            query=input_result.sanitized_text or message.body,
            tenant_id=tenant_id,
            top_k=5,
            actor_user_id=user_id,
            audit=False,
            enforce_guardrails=False,
        )
        memory_messages = await ConversationMemoryService().load_recent(
            tenant_id=tenant_id,
            conversation_id=conversation.id,
        )
        generated = await generate_reply_text_with_optional_llm(
            rag_result=rag_result,
            message_body=input_result.sanitized_text or message.body,
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
