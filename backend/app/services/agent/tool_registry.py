"""Registry for the bounded EventSense agent tools."""
from __future__ import annotations

from app.services.agent.tool_types import (
    TOOL_CREATE_FOLLOW_UP_TASK,
    TOOL_ESCALATE_TO_MANAGER,
    TOOL_RAG_SEARCH,
    TOOL_SUGGEST_REPLY,
    AgentToolName,
    BaseAgentTool,
)
from app.services.agent.tools import (
    CreateFollowUpTaskTool,
    EscalateToManagerTool,
    RagSearchTool,
    SuggestReplyTool,
)


EXPECTED_AGENT_TOOL_NAMES = frozenset(
    {
        TOOL_RAG_SEARCH,
        TOOL_SUGGEST_REPLY,
        TOOL_CREATE_FOLLOW_UP_TASK,
        TOOL_ESCALATE_TO_MANAGER,
    }
)


class UnknownAgentToolError(ValueError):
    pass


class UnapprovedAgentToolError(ValueError):
    pass


class AgentToolRegistry:
    def __init__(self, tools: list[BaseAgentTool]) -> None:
        tool_names = [tool.name for tool in tools]
        unknown_tools = sorted(set(tool_names) - EXPECTED_AGENT_TOOL_NAMES)
        if unknown_tools:
            raise UnapprovedAgentToolError(
                f"unapproved agent tools registered: {unknown_tools}"
            )
        duplicate_tools = sorted(
            tool_name for tool_name in set(tool_names) if tool_names.count(tool_name) > 1
        )
        if duplicate_tools:
            raise UnapprovedAgentToolError(
                f"duplicate agent tools registered: {duplicate_tools}"
            )
        self._tools = {tool.name: tool for tool in tools}

    def get_tool(self, name: AgentToolName) -> BaseAgentTool:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise UnknownAgentToolError(f"unknown agent tool: {name}") from exc

    def list_tools(self) -> list[AgentToolName]:
        return list(self._tools)


def create_default_tool_registry() -> AgentToolRegistry:
    return AgentToolRegistry(
        [
            RagSearchTool(),
            SuggestReplyTool(),
            CreateFollowUpTaskTool(),
            EscalateToManagerTool(),
        ]
    )
