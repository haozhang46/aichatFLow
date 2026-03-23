from __future__ import annotations

from typing import Any

from app.runtime.platform_tool_adapter import PlatformToolAdapter


class PlatformFileAdapter:
    def __init__(self, tool_adapter: PlatformToolAdapter) -> None:
        self._tool_adapter = tool_adapter

    async def read(self, path: str, *, user_id: str, agent_id: str, allowed_tool_ids: list[str], trace_id: str) -> dict[str, Any]:
        return await self._tool_adapter.execute(
            "file-read",
            {"path": path},
            user_id=user_id,
            agent_id=agent_id,
            allowed_tool_ids=allowed_tool_ids,
            trace_id=trace_id,
        )

    async def write(
        self,
        path: str,
        content: str,
        *,
        user_id: str,
        agent_id: str,
        allowed_tool_ids: list[str],
        trace_id: str,
    ) -> dict[str, Any]:
        return await self._tool_adapter.execute(
            "file-write",
            {"path": path, "content": content},
            user_id=user_id,
            agent_id=agent_id,
            allowed_tool_ids=allowed_tool_ids,
            trace_id=trace_id,
        )

    async def patch(
        self,
        path: str,
        content: str,
        mode: str,
        *,
        user_id: str,
        agent_id: str,
        allowed_tool_ids: list[str],
        trace_id: str,
    ) -> dict[str, Any]:
        return await self._tool_adapter.execute(
            "file-patch",
            {"path": path, "content": content, "mode": mode},
            user_id=user_id,
            agent_id=agent_id,
            allowed_tool_ids=allowed_tool_ids,
            trace_id=trace_id,
        )

    async def mkdir(
        self,
        path: str,
        *,
        user_id: str,
        agent_id: str,
        allowed_tool_ids: list[str],
        trace_id: str,
    ) -> dict[str, Any]:
        return await self._tool_adapter.execute(
            "file-mkdir",
            {"path": path},
            user_id=user_id,
            agent_id=agent_id,
            allowed_tool_ids=allowed_tool_ids,
            trace_id=trace_id,
        )

    async def delete(
        self,
        path: str,
        *,
        user_id: str,
        agent_id: str,
        allowed_tool_ids: list[str],
        trace_id: str,
    ) -> dict[str, Any]:
        return await self._tool_adapter.execute(
            "file-delete",
            {"path": path},
            user_id=user_id,
            agent_id=agent_id,
            allowed_tool_ids=allowed_tool_ids,
            trace_id=trace_id,
        )
