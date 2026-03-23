from __future__ import annotations

from typing import Any

import httpx


class ToolExecutorAdapterService:
    def __init__(self, builtin_registry: Any) -> None:
        self._builtin_registry = builtin_registry

    async def execute(
        self,
        manifest: dict[str, Any],
        args: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        kind = str(manifest.get("kind") or "").strip().lower()
        if kind == "http":
            return await self._execute_http(manifest, args, context=context)
        if kind == "builtin":
            return await self._execute_builtin(manifest, args, context=context)
        if kind == "file":
            return await self._execute_file(manifest, args, context=context)
        raise ValueError(f"tool kind `{kind}` is not supported yet")

    async def _execute_http(
        self,
        manifest: dict[str, Any],
        args: dict[str, Any],
        *,
        context: dict[str, Any] | None,
    ) -> dict[str, Any]:
        endpoint = manifest.get("endpoint") if isinstance(manifest.get("endpoint"), dict) else {}
        url = str(endpoint.get("url") or "").strip()
        if not url:
            raise ValueError("http tool endpoint.url is required")
        timeout_ms = endpoint.get("timeoutMs")
        timeout = float(timeout_ms) / 1000 if isinstance(timeout_ms, int) and timeout_ms > 0 else 15.0
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json={"args": args, "context": context or {}})
            response.raise_for_status()
            payload = response.json()
        if not isinstance(payload, dict):
            return {"result": payload}
        return payload

    async def _execute_builtin(
        self,
        manifest: dict[str, Any],
        args: dict[str, Any],
        *,
        context: dict[str, Any] | None,
    ) -> dict[str, Any]:
        endpoint = manifest.get("endpoint") if isinstance(manifest.get("endpoint"), dict) else {}
        target_tool_id = str(endpoint.get("toolId") or "").strip()
        if not target_tool_id:
            raise ValueError("builtin tool endpoint.toolId is required")
        return await self._builtin_registry.execute_builtin(target_tool_id, args, context=context)

    async def _execute_file(
        self,
        manifest: dict[str, Any],
        args: dict[str, Any],
        *,
        context: dict[str, Any] | None,
    ) -> dict[str, Any]:
        endpoint = manifest.get("endpoint") if isinstance(manifest.get("endpoint"), dict) else {}
        operation = str(endpoint.get("operation") or "").strip().lower()
        file_tool_map = {
            "list": "file-list",
            "read": "file-read",
            "write": "file-write",
            "delete": "file-delete",
            "mkdir": "file-mkdir",
            "patch": "file-patch",
        }
        target_tool_id = file_tool_map.get(operation)
        if not target_tool_id:
            raise ValueError("file tool endpoint.operation must be one of: list, read, write, delete, mkdir, patch")
        return await self._builtin_registry.execute_builtin(target_tool_id, args, context=context)
