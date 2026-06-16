"""Follow-up task agent tool."""
from __future__ import annotations

from app.repositories.task_repository import TaskRepository
from app.schemas.agent import AgentToolTrace
from app.schemas.task import TaskCreate
from app.services.agent.tool_types import (
    AGENT_SOURCE_TYPE,
    MODE_DRY_RUN,
    STATUS_RECOMMENDED,
    STATUS_SUCCESS,
    TOOL_CREATE_FOLLOW_UP_TASK,
    AgentToolAuditEvent,
    AgentToolContext,
    AgentToolMode,
    AgentToolResult,
    BaseAgentTool,
    input_summary,
    readable_intent,
    task_description,
    task_title,
)
from app.services.audit_log_service import AUDIT_EVENT_AGENT_TASK_CREATED
from app.services.task_service import TaskService


class CreateFollowUpTaskTool(BaseAgentTool):
    name = TOOL_CREATE_FOLLOW_UP_TASK
    description = "Recommend or create/reuse an idempotent staff follow-up task."

    async def run(
        self,
        context: AgentToolContext,
        mode: AgentToolMode,
    ) -> AgentToolResult:
        if mode == MODE_DRY_RUN:
            return AgentToolResult(
                trace=AgentToolTrace(
                    tool_name=TOOL_CREATE_FOLLOW_UP_TASK,
                    status=STATUS_RECOMMENDED,
                    mode=mode,
                    summary=f"Recommended follow-up task for {readable_intent(context.decision)}.",
                    input_summary=input_summary(context.message),
                    output_summary=task_title(context.decision),
                    recommended={
                        "title": task_title(context.decision),
                        "description": task_description(context.decision, context.message),
                    },
                )
            )

        existing_task = await TaskRepository(context.session).find_by_source(
            context.tenant_context.tenant_id,
            source_type=AGENT_SOURCE_TYPE,
            source_message_id=context.message.id,
        )
        audit_events: list[AgentToolAuditEvent] = []
        if existing_task is not None:
            task_id = existing_task.id
        else:
            task = await TaskService(context.session).create_task(
                TaskCreate(
                    conversation_id=context.conversation.id,
                    message_id=context.message.id,
                    title=task_title(context.decision),
                    description=task_description(context.decision, context.message),
                    assigned_to_user_id=context.tenant_context.user_id,
                ),
                context.tenant_context,
                source_type=AGENT_SOURCE_TYPE,
                source_message_id=context.message.id,
            )
            task_id = task.id
            audit_events.append(
                AgentToolAuditEvent(
                    event_type=AUDIT_EVENT_AGENT_TASK_CREATED,
                    resource_type="task",
                    resource_id=task.id,
                    details={"source_type": AGENT_SOURCE_TYPE},
                )
            )
        if context.applied is not None:
            context.applied.task_id = task_id
        return AgentToolResult(
            trace=AgentToolTrace(
                tool_name=TOOL_CREATE_FOLLOW_UP_TASK,
                status=STATUS_SUCCESS,
                mode=mode,
                summary="Created or reused follow-up task.",
                input_summary=input_summary(context.message),
                output_summary=task_title(context.decision),
                created_id=task_id,
            ),
            audit_events=audit_events,
        )
