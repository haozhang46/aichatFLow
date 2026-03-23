from __future__ import annotations

from typing import Any

from app.services.platform_trace_service import PlatformTraceService


class PlatformTraceAdapter:
    def __init__(self, platform_trace_service: PlatformTraceService) -> None:
        self._platform_trace_service = platform_trace_service

    def emit_run_started(self, *, trace_id: str, run_id: str, agent_id: str, user_id: str, metadata: dict[str, Any]) -> None:
        self._platform_trace_service.emit(
            trace_id,
            "run_started",
            run_id=run_id,
            span_id=self._platform_trace_service.new_span_id("deepagent"),
            status="running",
            agentId=agent_id,
            userId=user_id,
            metadata=metadata,
        )

    def emit_run_completed(
        self,
        *,
        trace_id: str,
        run_id: str,
        agent_id: str,
        user_id: str,
        status: str,
        metadata: dict[str, Any],
    ) -> None:
        self._platform_trace_service.emit(
            trace_id,
            "run_completed",
            run_id=run_id,
            span_id=self._platform_trace_service.new_span_id("deepagent"),
            status=status,
            agentId=agent_id,
            userId=user_id,
            metadata=metadata,
        )

    def emit_step_started(self, *, trace_id: str, run_id: str, step_id: str, agent_id: str, metadata: dict[str, Any]) -> None:
        self._platform_trace_service.emit(
            trace_id,
            "step_started",
            run_id=run_id,
            span_id=step_id,
            status="success",
            agentId=agent_id,
            metadata=metadata,
        )

    def emit_step_completed(self, *, trace_id: str, run_id: str, step_id: str, agent_id: str, metadata: dict[str, Any]) -> None:
        self._platform_trace_service.emit(
            trace_id,
            "step_completed",
            run_id=run_id,
            span_id=self._platform_trace_service.new_span_id("deepagent-step"),
            parent_span_id=step_id,
            status="success",
            agentId=agent_id,
            metadata=metadata,
        )

    def emit_replanned(self, *, trace_id: str, run_id: str, step_id: str, agent_id: str, metadata: dict[str, Any]) -> None:
        self._platform_trace_service.emit(
            trace_id,
            "replanned",
            run_id=run_id,
            span_id=self._platform_trace_service.new_span_id("deepagent-replan"),
            parent_span_id=step_id,
            status="success",
            agentId=agent_id,
            metadata=metadata,
        )
