from __future__ import annotations

from typing import Any

from app.contracts.otie import ExecutionPlan, IntentEnvelope
from app.memory.plan_store import PlanStore
from app.services.trace_store import TraceStore


class OtieTraceService:
    def __init__(self, trace_store: TraceStore, plan_store: PlanStore) -> None:
        self._trace_store = trace_store
        self._plan_store = plan_store

    def append_event(self, run_id: str, event_type: str, **payload: Any) -> None:
        self._trace_store.append(run_id, {"type": event_type, **payload})

    def start_run(self, run_id: str, intent: IntentEnvelope, plan: ExecutionPlan) -> None:
        self._plan_store.save(plan)
        self.append_event(
            run_id,
            "run_started",
            requestId=intent.request_id,
            tenantId=intent.tenant_id,
            intent=intent.model_dump(by_alias=True),
            plan=plan.model_dump(by_alias=True),
            status="running",
        )

    def finish_run(self, run_id: str, *, status: str, final_answer: str, step_outputs: dict[str, Any]) -> None:
        self.append_event(
            run_id,
            "run_finished",
            status=status,
            finalAnswer=final_answer,
            stepOutputs=step_outputs,
        )

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        events = self._trace_store.read_trace(run_id)
        if not events:
            return None

        run: dict[str, Any] = {
            "runId": run_id,
            "traceId": run_id,
            "status": "unknown",
            "intent": None,
            "plan": None,
            "finalAnswer": "",
            "stepOutputs": {},
            "events": events,
        }
        for event in events:
            etype = event.get("type")
            if etype == "run_started":
                run["status"] = event.get("status", "running")
                run["intent"] = event.get("intent")
                run["plan"] = event.get("plan")
            elif etype == "state_transition":
                run["status"] = event.get("toState", run["status"])
            elif etype == "run_finished":
                run["status"] = event.get("status", run["status"])
                run["finalAnswer"] = event.get("finalAnswer", "")
                run["stepOutputs"] = event.get("stepOutputs", {})
        return run
