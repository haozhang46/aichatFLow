from __future__ import annotations

import inspect
import json
from datetime import datetime
from typing import Any

from app.services.schema_validation import validate_against_schema
from app.tools.base import Tool


class ToolRegistry:
    def __init__(
        self,
        tools: list[Tool],
        *,
        definition_registry: Any | None = None,
        executor_adapter: Any | None = None,
        platform_trace_service: Any | None = None,
    ) -> None:
        self._tools = {tool.tool_id: tool for tool in tools}
        self._definition_registry = definition_registry
        self._executor_adapter = executor_adapter
        self._platform_trace_service = platform_trace_service

    def has_tool(self, tool_id: str) -> bool:
        return tool_id in self._tools or self._get_custom_tool(tool_id) is not None

    def get_tool(self, tool_id: str) -> Tool | None:
        return self._tools.get(tool_id)

    def execute_builtin(
        self,
        tool_id: str,
        args: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> Any:
        return self.execute(tool_id, args, context=context, builtin_only=True)

    async def execute(
        self,
        tool_id: str,
        args: dict[str, Any],
        context: dict[str, Any] | None = None,
        *,
        builtin_only: bool = False,
    ) -> dict[str, Any]:
        exec_context = context if context is not None else {}
        trace_id, root_span_id = self._start_tool_trace(tool_id, args, exec_context)
        descriptor = self.describe_tool(tool_id) or {"id": tool_id}
        tool = self._tools.get(tool_id)
        try:
            self._validate_invocation(tool_id, args, exec_context, descriptor)
            if tool is not None:
                params = inspect.signature(tool.execute).parameters
                if "context" in params:
                    result = await tool.execute(args, context=exec_context)
                else:
                    result = await tool.execute(args)
                self._validate_output(tool_id, result, descriptor)
                self._finish_tool_trace(trace_id, root_span_id, tool_id, exec_context, result)
                return result
            if builtin_only:
                raise ValueError(f"builtin tool `{tool_id}` is not registered")
            custom_tool = self._get_custom_tool(tool_id)
            if custom_tool is None:
                raise ValueError(f"tool `{tool_id}` is not registered")
            if self._executor_adapter is None:
                raise ValueError(f"tool `{tool_id}` has no executor adapter")
            result = await self._executor_adapter.execute(custom_tool, args, context=exec_context)
            self._validate_output(tool_id, result, descriptor)
            self._finish_tool_trace(trace_id, root_span_id, tool_id, exec_context, result)
            return result
        except Exception as exc:
            self._fail_tool_trace(trace_id, root_span_id, tool_id, exec_context, exc)
            raise

    def list_tools(self) -> list[str]:
        return sorted(self._tools)

    def describe_tools(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for tool_id in sorted(self._tools):
            tool = self._tools[tool_id]
            items.append(self._builtin_descriptor(tool_id, tool))
        return items

    def describe_tool(self, tool_id: str) -> dict[str, Any] | None:
        tool = self._tools.get(tool_id)
        if tool is None:
            custom = self._get_custom_tool(tool_id)
            if custom is None:
                return None
            return custom
        return self._builtin_descriptor(tool_id, tool)

    def _get_custom_tool(self, tool_id: str) -> dict[str, Any] | None:
        if self._definition_registry is None:
            return None
        record = self._definition_registry.get_tool(tool_id)
        if not isinstance(record, dict):
            return None
        if str(record.get("status") or "") != "published":
            return None
        return record

    def _start_tool_trace(
        self,
        tool_id: str,
        args: dict[str, Any],
        context: dict[str, Any],
    ) -> tuple[str, str]:
        if self._platform_trace_service is None:
            return "", ""
        trace_id = str(context.get("traceId") or "").strip() or self._platform_trace_service.new_trace_id("tool")
        span_id = self._platform_trace_service.new_span_id("toolcall")
        context["traceId"] = trace_id
        self._platform_trace_service.emit(
            trace_id,
            "tool_call_started",
            run_id=trace_id,
            span_id=span_id,
            parent_span_id=str(context.get("parentSpanId") or "").strip() or None,
            status="success",
            toolId=tool_id,
            userId=str(context.get("currentUserId") or "").strip(),
            metadata={"args": args, "source": str(context.get("traceSource") or "tool_registry")},
        )
        return trace_id, span_id

    def _finish_tool_trace(
        self,
        trace_id: str,
        root_span_id: str,
        tool_id: str,
        context: dict[str, Any],
        result: Any,
    ) -> None:
        if self._platform_trace_service is None or not trace_id:
            return
        self._platform_trace_service.emit(
            trace_id,
            "tool_call_completed",
            run_id=trace_id,
            span_id=self._platform_trace_service.new_span_id("toolcall"),
            parent_span_id=root_span_id or None,
            status="success",
            toolId=tool_id,
            userId=str(context.get("currentUserId") or "").strip(),
            metadata={
                "resultPreview": self._preview_result(result),
                "source": str(context.get("traceSource") or "tool_registry"),
            },
        )

    def _fail_tool_trace(
        self,
        trace_id: str,
        root_span_id: str,
        tool_id: str,
        context: dict[str, Any],
        exc: Exception,
    ) -> None:
        if self._platform_trace_service is None or not trace_id:
            return
        self._platform_trace_service.emit(
            trace_id,
            "tool_call_failed",
            run_id=trace_id,
            span_id=self._platform_trace_service.new_span_id("toolcall"),
            parent_span_id=root_span_id or None,
            status="failed",
            toolId=tool_id,
            userId=str(context.get("currentUserId") or "").strip(),
            metadata={
                "error": {"message": str(exc)},
                "source": str(context.get("traceSource") or "tool_registry"),
            },
        )

    def _preview_result(self, result: Any) -> str:
        try:
            return json.dumps(result, ensure_ascii=False)[:500]
        except Exception:
            return str(result)[:500]

    def _builtin_descriptor(self, tool_id: str, tool: Tool) -> dict[str, Any]:
        now = datetime.utcnow().isoformat()
        return {
            "id": tool_id,
            "name": str(getattr(tool, "display_name", tool_id)),
            "description": str(getattr(tool, "description", "")),
            "version": str(getattr(tool, "version", "0.1.0")),
            "kind": "builtin",
            "category": str(getattr(tool, "category", "general")),
            "builtin": True,
            "inputSchema": getattr(tool, "input_schema", {"type": "object", "additionalProperties": True}),
            "outputSchema": getattr(tool, "output_schema", {"type": "object", "additionalProperties": True}),
            "requiredUserInputs": getattr(tool, "required_user_inputs", []),
            "exampleArgs": getattr(tool, "example_args", None),
            "uiPlugin": getattr(tool, "ui_plugin", None),
            "uiSchema": getattr(tool, "ui_schema", None),
            "auth": {"mode": "user", "requiresCookie": False},
            "policy": {"riskLevel": "medium", "allowAgents": []},
            "source": {"type": "core", "path": f"builtin:{tool_id}"},
            "status": "published",
            "lifecycle": {
                "entityType": "tool",
                "entityId": tool_id,
                "version": str(getattr(tool, "version", "0.1.0")),
                "state": "published",
                "validation": {"status": "passed", "errors": []},
                "review": {"status": "not_required"},
                "source": {"kind": "manual"},
                "createdAt": now,
                "updatedAt": now,
                "publishedAt": now,
            },
        }

    def _validate_invocation(
        self,
        tool_id: str,
        args: dict[str, Any],
        context: dict[str, Any],
        descriptor: dict[str, Any],
    ) -> None:
        allowed_tool_ids = context.get("allowedToolIds")
        if isinstance(allowed_tool_ids, (list, tuple, set)):
            normalized_allowed = {str(item).strip() for item in allowed_tool_ids if str(item).strip()}
            if normalized_allowed and tool_id not in normalized_allowed:
                raise PermissionError(f"tool `{tool_id}` is not in the agent allowedTools whitelist")

        policy = descriptor.get("policy") if isinstance(descriptor.get("policy"), dict) else {}
        allow_agents = policy.get("allowAgents") if isinstance(policy.get("allowAgents"), list) else []
        current_agent_id = str(context.get("currentAgentId") or context.get("agentId") or "").strip()
        if allow_agents and current_agent_id and current_agent_id not in {str(item).strip() for item in allow_agents}:
            raise PermissionError(f"tool `{tool_id}` is not allowed for agent `{current_agent_id}`")

        input_schema = descriptor.get("inputSchema")
        if isinstance(input_schema, dict) and input_schema:
            validation = validate_against_schema(args, input_schema)
            if not validation.ok:
                raise ValueError(f"tool `{tool_id}` args invalid: {validation.error}")

    def _validate_output(self, tool_id: str, result: Any, descriptor: dict[str, Any]) -> None:
        output_schema = descriptor.get("outputSchema")
        if isinstance(output_schema, dict) and output_schema:
            validation = validate_against_schema(result, output_schema)
            if not validation.ok:
                raise ValueError(f"tool `{tool_id}` output invalid: {validation.error}")
