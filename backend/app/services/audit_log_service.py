from datetime import date, datetime
from enum import Enum
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog


AUDIT_EVENT_AUTH_LOGIN_SUCCESS = "auth.login_success"
AUDIT_EVENT_AUTH_LOGIN_FAILED = "auth.login_failed"
AUDIT_EVENT_AUTH_LOGOUT = "auth.logout"
AUDIT_EVENT_SIMULATOR_MESSAGE_RECEIVED = "simulator.message_received"
AUDIT_EVENT_TELEGRAM_MESSAGE_RECEIVED = "telegram.message_received"
AUDIT_EVENT_TELEGRAM_REPLY_SENT = "telegram.reply_sent"
AUDIT_EVENT_TELEGRAM_AUTO_REPLY_SENT = "telegram.auto_reply_sent"
AUDIT_EVENT_TELEGRAM_AUTO_REPLY_SKIPPED = "telegram.auto_reply_skipped"
AUDIT_EVENT_MESSAGE_INTENT_CLASSIFIED = "message.intent_classified"
AUDIT_EVENT_MESSAGE_RISK_DETECTED = "message.risk_detected"
AUDIT_EVENT_CONVERSATION_DETAIL_VIEWED = "conversation.detail_viewed"
AUDIT_EVENT_CONVERSATION_STATUS_CHANGED = "conversation.status_changed"
AUDIT_EVENT_TENANT_CROSS_TENANT_ACCESS_BLOCKED = "tenant.cross_tenant_access_blocked"
AUDIT_EVENT_TASK_CREATED = "task.created"
AUDIT_EVENT_TASK_UPDATED = "task.updated"
AUDIT_EVENT_TASK_STATUS_CHANGED = "task.status_changed"
AUDIT_EVENT_ESCALATION_CREATED = "escalation.created"
AUDIT_EVENT_ESCALATION_UPDATED = "escalation.updated"
AUDIT_EVENT_ESCALATION_STATUS_CHANGED = "escalation.status_changed"
AUDIT_EVENT_ESCALATION_RESOLVED = "escalation.resolved"
AUDIT_EVENT_AGENT_DECISION_CREATED = "agent.decision_created"
AUDIT_EVENT_AGENT_SKIPPED = "agent.skipped"
AUDIT_EVENT_AGENT_STARTED = "agent.started"
AUDIT_EVENT_AGENT_TOOL_PLANNED = "agent.tool_planned"
AUDIT_EVENT_AGENT_TOOL_EXECUTED = "agent.tool_executed"
AUDIT_EVENT_AGENT_TOOL_FAILED = "agent.tool_failed"
AUDIT_EVENT_AGENT_COMPLETED = "agent.completed"
AUDIT_EVENT_AGENT_TASK_CREATED = "agent.task_created"
AUDIT_EVENT_AGENT_ESCALATION_CREATED = "agent.escalation_created"
AUDIT_EVENT_AGENT_SUGGESTED_REPLY_DRAFTED = "agent.suggested_reply_drafted"
AUDIT_EVENT_AGENT_HUMAN_REVIEW_REQUIRED = "agent.human_review_required"
AUDIT_EVENT_DOCUMENT_CREATED = "document.created"
AUDIT_EVENT_DOCUMENT_UPDATED = "document.updated"
AUDIT_EVENT_DOCUMENT_ARCHIVED = "document.archived"
AUDIT_EVENT_DOCUMENT_CHUNKED_INDEXED = "document.chunked_indexed"
AUDIT_EVENT_RAG_QUERY_EXECUTED = "rag.query_executed"
AUDIT_EVENT_RAG_NO_SOURCE_REFUSAL = "rag.no_source_refusal"
AUDIT_EVENT_RAG_RETRIEVAL_RETURNED_SOURCES = "rag.retrieval_returned_sources"
AUDIT_EVENT_SUGGESTED_REPLY_GENERATED = "suggested_reply.generated"
AUDIT_EVENT_SUGGESTED_REPLY_REFUSED_NO_SOURCE = "suggested_reply.refused_no_source"
AUDIT_EVENT_SUGGESTED_REPLY_APPROVED = "suggested_reply.approved"
AUDIT_EVENT_SUGGESTED_REPLY_EDITED = "suggested_reply.edited"
AUDIT_EVENT_SUGGESTED_REPLY_REJECTED = "suggested_reply.rejected"
AUDIT_EVENT_GUARDRAIL_INPUT_BLOCKED = "guardrail_input_blocked"
AUDIT_EVENT_GUARDRAIL_INPUT_REDACTED = "guardrail_input_redacted"
AUDIT_EVENT_GUARDRAIL_RETRIEVAL_REDACTED = "guardrail_retrieval_redacted"
AUDIT_EVENT_GUARDRAIL_RETRIEVAL_BLOCKED = "guardrail_retrieval_blocked"
AUDIT_EVENT_GUARDRAIL_OUTPUT_REDACTED = "guardrail_output_redacted"
AUDIT_EVENT_GUARDRAIL_OUTPUT_BLOCKED = "guardrail_output_blocked"
AUDIT_EVENT_GUARDRAIL_CROSS_TENANT_BLOCKED = "guardrail_cross_tenant_blocked"
AUDIT_EVENT_GUARDRAIL_SYSTEM_PROMPT_BLOCKED = "guardrail_system_prompt_blocked"


def _json_safe(value: object) -> object:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set):
        return [_json_safe(item) for item in value]
    return value


class AuditLogService:
    @staticmethod
    def record(
        session: AsyncSession,
        *,
        tenant_id: UUID,
        event_type: str,
        actor_user_id: UUID | None = None,
        resource_type: str | None = None,
        resource_id: UUID | str | None = None,
        details: dict[str, object] | None = None,
    ) -> AuditLog:
        audit_log = AuditLog(
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            event_type=event_type,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id is not None else None,
            details=_json_safe(details or {}),
        )
        session.add(audit_log)
        return audit_log

    @staticmethod
    async def list_for_tenant(
        session: AsyncSession,
        *,
        tenant_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditLog]:
        result = await session.execute(
            select(AuditLog)
            .where(AuditLog.tenant_id == tenant_id)
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())
