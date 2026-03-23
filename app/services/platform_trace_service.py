from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.services.trace_store import TraceStore


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class PlatformTraceService:
    def __init__(self, trace_store: TraceStore) -> None:
        self._trace_store = trace_store

    def new_trace_id(self, prefix: str = "trace") -> str:
        return f"{prefix}_{uuid4().hex[:12]}"

    def new_span_id(self, prefix: str = "span") -> str:
        return f"{prefix}_{uuid4().hex[:12]}"

    def emit(
        self,
        trace_id: str,
        event_type: str,
        *,
        run_id: str | None = None,
        span_id: str | None = None,
        parent_span_id: str | None = None,
        status: str | None = None,
        **payload: Any,
    ) -> None:
        event: dict[str, Any] = {
            "type": event_type,
            "timestamp": _utc_now_iso(),
            "runId": run_id or trace_id,
            "spanId": span_id or self.new_span_id(),
        }
        if parent_span_id:
            event["parentSpanId"] = parent_span_id
        if status:
            event["status"] = status
        event.update(payload)
        self._trace_store.append(trace_id, event)
