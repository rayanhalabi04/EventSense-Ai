"""Draft suggested reply agent tool."""
from __future__ import annotations

from uuid import UUID

from app.models.suggested_reply import SuggestedReply, SuggestedReplyStatus
from app.repositories.suggested_reply_repository import SuggestedReplyRepository
from app.schemas.agent import AgentToolTrace
from app.services.agent.tool_types import (
    MODE_APPLY,
    STATUS_DRAFT,
    STATUS_UNSUPPORTED,
    TOOL_SUGGEST_REPLY,
    AgentToolAuditEvent,
    AgentToolContext,
    AgentToolMode,
    AgentToolResult,
    BaseAgentTool,
    input_summary,
)
from app.services.audit_log_service import AUDIT_EVENT_AGENT_SUGGESTED_REPLY_DRAFTED
from app.services.rag_service import NO_SOURCE_MESSAGE, RagResult
from app.services.suggested_reply_service import generate_reply_text


class SuggestReplyTool(BaseAgentTool):
    name = TOOL_SUGGEST_REPLY
    description = "Prepare a draft reply preview, and save/reuse a draft in apply mode."

    async def run(
        self,
        context: AgentToolContext,
        mode: AgentToolMode,
    ) -> AgentToolResult:
        rag_result = context.rag_result or RagResult(
            query=context.message.body or "",
            answer_supported=False,
            sources=[],
            refusal_reason=NO_SOURCE_MESSAGE,
        )
        generated = generate_reply_text(
            rag_result=rag_result,
            message_body=context.message.body or "",
            risk_level=context.message.risk_level,
        )

        status_text = STATUS_DRAFT if generated.answer_supported else STATUS_UNSUPPORTED
        created_id: UUID | None = None
        audit_events: list[AgentToolAuditEvent] = []
        if mode == MODE_APPLY:
            reply = await self._create_or_reuse_suggested_reply(
                context=context,
                generated_text=generated.suggested_text,
                rag_sources=generated.rag_sources,
                source_document_ids=generated.source_document_ids,
                answer_supported=generated.answer_supported,
                refusal_reason=generated.refusal_reason,
                generation_method=generated.generation_method,
            )
            created_id = reply.id
            if context.applied is not None:
                context.applied.suggested_reply_id = reply.id
            audit_events.append(
                AgentToolAuditEvent(
                    event_type=AUDIT_EVENT_AGENT_SUGGESTED_REPLY_DRAFTED,
                    resource_type="suggested_reply",
                    resource_id=reply.id,
                    details={"status": "draft", "answer_supported": reply.answer_supported},
                )
            )

        trace = AgentToolTrace(
            tool_name=TOOL_SUGGEST_REPLY,
            status=status_text,
            mode=mode,
            summary="Prepared draft reply preview."
            if generated.answer_supported
            else "Prepared unsupported fallback for human review.",
            input_summary=input_summary(context.message),
            output_summary="Draft reply saved." if created_id is not None else "Draft reply preview only.",
            source_ids=generated.source_document_ids,
            suggested_reply_preview=generated.suggested_text,
            created_id=created_id,
        )
        return AgentToolResult(
            trace=trace,
            suggested_text=generated.suggested_text,
            human_review_required=not generated.answer_supported,
            confidence="low" if not generated.answer_supported else None,
            audit_events=audit_events,
        )

    @staticmethod
    async def _create_or_reuse_suggested_reply(
        *,
        context: AgentToolContext,
        generated_text: str,
        rag_sources: list[dict[str, object]],
        source_document_ids: list[str],
        answer_supported: bool,
        refusal_reason: str | None,
        generation_method: str,
    ) -> SuggestedReply:
        repository = SuggestedReplyRepository(context.session)
        existing = await repository.latest_for_message(
            context.tenant_context.tenant_id,
            context.message.id,
        )
        if existing is not None:
            return existing

        reply = SuggestedReply(
            tenant_id=context.tenant_context.tenant_id,
            conversation_id=context.conversation.id,
            message_id=context.message.id,
            suggested_text=generated_text,
            status=SuggestedReplyStatus.draft,
            source_document_ids=source_document_ids,
            rag_sources=rag_sources,
            answer_supported=answer_supported,
            refusal_reason=refusal_reason,
            generation_method=generation_method,
            created_by_user_id=context.tenant_context.user_id,
        )
        await repository.add(reply)
        return reply
