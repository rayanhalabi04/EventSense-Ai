"""Tenant-scoped RAG search agent tool."""
from __future__ import annotations

from app.schemas.agent import AgentToolTrace
from app.services.agent.tool_types import (
    STATUS_SUCCESS,
    STATUS_UNSUPPORTED,
    TOOL_RAG_SEARCH,
    AgentToolContext,
    AgentToolMode,
    AgentToolResult,
    BaseAgentTool,
    input_summary,
)
from app.services.rag_service import NO_SOURCE_MESSAGE, RagResult, retrieve


class RagSearchTool(BaseAgentTool):
    name = TOOL_RAG_SEARCH
    description = "Retrieve tenant-scoped document context for the client message."

    async def run(
        self,
        context: AgentToolContext,
        mode: AgentToolMode,
    ) -> AgentToolResult:
        rag_result = await retrieve(
            context.session,
            query=context.message.body or "",
            tenant_id=context.tenant_context.tenant_id,
            top_k=5,
            actor_user_id=context.tenant_context.user_id,
        )
        trace = self._trace(rag_result, mode=mode, context=context)
        return AgentToolResult(
            trace=trace,
            rag_result=rag_result,
            human_review_required=not rag_result.answer_supported,
            confidence="low" if not rag_result.answer_supported else None,
        )

    @staticmethod
    def _trace(
        rag_result: RagResult,
        *,
        mode: AgentToolMode,
        context: AgentToolContext,
    ) -> AgentToolTrace:
        source_ids = [str(source.document_id) for source in rag_result.sources]
        if rag_result.answer_supported:
            return AgentToolTrace(
                tool_name=TOOL_RAG_SEARCH,
                status=STATUS_SUCCESS,
                mode=mode,
                summary="Retrieved tenant document sources.",
                input_summary=input_summary(context.message),
                output_summary=f"Found {len(source_ids)} relevant sources.",
                source_ids=source_ids,
            )
        return AgentToolTrace(
            tool_name=TOOL_RAG_SEARCH,
            status=STATUS_UNSUPPORTED,
            mode=mode,
            summary="No supporting tenant document source found.",
            input_summary=input_summary(context.message),
            output_summary=rag_result.refusal_reason or NO_SOURCE_MESSAGE,
            source_ids=[],
        )
