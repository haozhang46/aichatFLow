from __future__ import annotations

from typing import Any, Protocol


class Tool(Protocol):
    tool_id: str

    async def execute(self, args: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
        ...
