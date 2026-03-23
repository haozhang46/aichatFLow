from __future__ import annotations

from typing import Any

from app.tools.registry import ToolRegistry


class PlatformToolAdapter:
    def __init__(self, tool_registry: ToolRegistry) -> None:
        self._tool_registry = tool_registry

    def list_allowed_tools(self, allowed_tool_ids: list[str]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for tool_id in [str(item).strip() for item in allowed_tool_ids if str(item).strip()]:
            descriptor = self._tool_registry.describe_tool(tool_id)
            if descriptor is not None:
                items.append(descriptor)
        return items

    async def execute(
        self,
        tool_id: str,
        args: dict[str, Any],
        *,
        user_id: str,
        agent_id: str,
        allowed_tool_ids: list[str],
        trace_id: str,
        parent_span_id: str | None = None,
    ) -> dict[str, Any]:
        return await self._tool_registry.execute(
            tool_id,
            args,
            context={
                "currentUserId": user_id,
                "currentAgentId": agent_id,
                "allowedToolIds": allowed_tool_ids,
                "traceId": trace_id,
                "traceSource": "deepagent_runtime",
                "parentSpanId": parent_span_id,
            },
        )
