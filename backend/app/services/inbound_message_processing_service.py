"""Shared inbound-message processing pipeline.

Every inbound channel (Telegram today, others later) routes a saved inbound
message through the *same* decision pipeline that powers the simulator and
suggested-reply flow:

    intent + risk (already attached to the message) -> suggested reply
    (tenant-scoped RAG + guardrails + audit) -> auto-send decision -> escalation.

The service is deliberately channel-agnostic. Auto-send is attempted only when
``auto_reply_channel`` matches the message source (``"telegram"``). Tenant
isolation is strict: the conversation and message are re-resolved against the
``tenant_id`` resolved upstream from the channel mapping, never from message
text. Cross-tenant references are refused and never auto-sent.

The returned :class:`InboundDecision` is a plain, serialisable summary of what
happened, suitable for webhook responses, logs, and tests.
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message import Message
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.message_repository import MessageRepository
from app.services.escalation_service import EscalationService
from app.services.telegram_auto_reply_service import (
    AutoReplyDecision,
    TelegramAutoReplyService,
)
from app.services.telegram_service import TELEGRAM_SOURCE, TelegramService


# Intents that must never auto-send and that should be routed to a human via a
# manager escalation. Mirrors the agent trigger intents (complaint,
# cancellation_request, payment_issue, urgent_change, human_escalation,
# guest_count_change) so Telegram and the agent stay consistent.
ESCALATION_INTENTS = frozenset(
    {
        "complaint",
        "cancellation_request",
        "payment_issue",
        "urgent_change",
        "human_escalation",
        "guest_count_change",
    }
)

RISK_LEVEL_HIGH = "high"

# Provenance marker for escalations created by this pipeline (keeps creation
# idempotent across webhook retries via EscalationRepository.find_by_source).
INBOUND_ESCALATION_SOURCE_TYPE = "inbound_auto"

ACTION_AUTO_SENT = "auto_sent"
ACTION_HUMAN_REVIEW = "human_review"
ACTION_ESCALATED = "escalated"
ACTION_REFUSED = "refused"

REASON_GUARDRAIL_REFUSAL = "guardrail_refusal"
REASON_CROSS_TENANT = "cross_tenant_reference"
REASON_AUTO_REPLY_CHANNEL_DISABLED = "auto_reply_channel_disabled"


@dataclass(frozen=True)
class InboundDecision:
    message_id: UUID | None
    intent_label: str | None
    risk_level: str | None
    rag_supported: bool
    guardrail_allowed: bool
    auto_send_allowed: bool
    action: str
    reason: str | None
    suggested_reply_id: UUID | None = None
    escalation_id: UUID | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "message_id": str(self.message_id) if self.message_id is not None else None,
            "intent_label": self.intent_label,
            "risk_level": self.risk_level,
            "rag_supported": self.rag_supported,
            "guardrail_allowed": self.guardrail_allowed,
            "auto_send_allowed": self.auto_send_allowed,
            "action": self.action,
            "reason": self.reason,
            "suggested_reply_id": (
                str(self.suggested_reply_id) if self.suggested_reply_id is not None else None
            ),
            "escalation_id": str(self.escalation_id) if self.escalation_id is not None else None,
        }


class InboundMessageProcessingService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        telegram: TelegramService | None = None,
    ) -> None:
        self.session = session
        self.telegram = telegram

    async def process_inbound_message(
        self,
        *,
        tenant_id: UUID,
        conversation_id: UUID,
        message_id: UUID,
        source: str,
        auto_reply_channel: str | None = None,
    ) -> InboundDecision:
        conversation = await ConversationRepository(self.session).get(conversation_id)
        if conversation is None or conversation.tenant_id != tenant_id:
            return self._refused(message_id, REASON_CROSS_TENANT)

        message = await MessageRepository(self.session).get(message_id)
        if (
            message is None
            or message.tenant_id != tenant_id
            or message.conversation_id != conversation_id
        ):
            return self._refused(message_id, REASON_CROSS_TENANT)

        # Run the auto-reply decision (suggested reply generation, tenant-scoped
        # RAG, guardrails, and audit) only when the caller asks this exact channel
        # to auto-reply. Low-risk normal questions are handled entirely here; the
        # heavier agent is only consulted for risky/complex cases below.
        auto_reply: AutoReplyDecision | None = None
        if auto_reply_channel == source == TELEGRAM_SOURCE:
            auto_reply = await TelegramAutoReplyService(self.telegram).maybe_auto_reply(
                self.session,
                conversation=conversation,
                message=message,
            )

        suggested = auto_reply.suggested_reply if auto_reply is not None else None
        sent = bool(auto_reply is not None and auto_reply.sent)
        reason = (
            auto_reply.reason
            if auto_reply is not None
            else REASON_AUTO_REPLY_CHANNEL_DISABLED
        )

        rag_supported = bool(
            suggested is not None and suggested.answer_supported and suggested.rag_sources
        )
        guardrail_allowed = reason != REASON_GUARDRAIL_REFUSAL

        if sent:
            return InboundDecision(
                message_id=message.id,
                intent_label=message.intent_label,
                risk_level=message.risk_level,
                rag_supported=rag_supported,
                guardrail_allowed=guardrail_allowed,
                auto_send_allowed=True,
                action=ACTION_AUTO_SENT,
                reason=None,
                suggested_reply_id=suggested.id if suggested is not None else None,
                escalation_id=None,
            )

        # Not auto-sent: route to a human. Risky/complex intents and any high-risk
        # message become a manager escalation; everything else is a human-review
        # recommendation (the suggested reply stays a pending staff draft).
        needs_escalation = (
            message.intent_label in ESCALATION_INTENTS
            or message.risk_level == RISK_LEVEL_HIGH
        )

        escalation_id: UUID | None = None
        if needs_escalation:
            escalation = await EscalationService(self.session).create_automated_escalation(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                message=message,
                reason=reason or "needs_human_review",
                ai_summary=_escalation_summary(message),
                suggested_next_step="Manager review recommended by the inbound pipeline.",
                source_type=INBOUND_ESCALATION_SOURCE_TYPE,
                source_message_id=message.id,
            )
            escalation_id = escalation.id
            action = ACTION_ESCALATED
        elif not guardrail_allowed:
            action = ACTION_REFUSED
        else:
            action = ACTION_HUMAN_REVIEW

        return InboundDecision(
            message_id=message.id,
            intent_label=message.intent_label,
            risk_level=message.risk_level,
            rag_supported=rag_supported,
            guardrail_allowed=guardrail_allowed,
            auto_send_allowed=False,
            action=action,
            reason=reason,
            suggested_reply_id=suggested.id if suggested is not None else None,
            escalation_id=escalation_id,
        )

    @staticmethod
    def _refused(message_id: UUID | None, reason: str) -> InboundDecision:
        return InboundDecision(
            message_id=message_id,
            intent_label=None,
            risk_level=None,
            rag_supported=False,
            guardrail_allowed=False,
            auto_send_allowed=False,
            action=ACTION_REFUSED,
            reason=reason,
        )


def _escalation_summary(message: Message) -> str:
    intent = message.intent_label or "unclassified"
    risk = message.risk_level or "unknown"
    return (
        f"Inbound {message.source or 'message'} classified as {intent} "
        f"(risk: {risk}) was not auto-sent and needs manager review."
    )
