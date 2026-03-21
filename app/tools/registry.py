from __future__ import annotations

from typing import Any

from app.tools.base import Tool


class ToolRegistry:
    def __init__(self, tools: list[Tool]) -> None:
        self._tools = {tool.tool_id: tool for tool in tools}

    def has_tool(self, tool_id: str) -> bool:
        return tool_id in self._tools

    async def execute(self, tool_id: str, args: dict[str, Any]) -> dict[str, Any]:
        tool = self._tools.get(tool_id)
        if tool is None:
            raise ValueError(f"tool `{tool_id}` is not registered")
        return await tool.execute(args)

    def list_tools(self) -> list[str]:
        return sorted(self._tools)

    def describe_tools(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for tool_id in sorted(self._tools):
            tool = self._tools[tool_id]
            items.append(
                {
                    "id": tool_id,
                    "name": str(getattr(tool, "display_name", tool_id)),
                    "description": str(getattr(tool, "description", "")),
                    "category": str(getattr(tool, "category", "general")),
                    "builtin": True,
                }
            )
        return items
