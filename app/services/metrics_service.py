"""In-memory KPI counters (single-process MVP). Replace with Redis/DB for multi-instance."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MetricsService:
    plan_total: int = 0
    plan_success: int = 0
    tool_calls: int = 0
    tool_failures: int = 0
    schema_checks: int = 0
    schema_ok: int = 0

    def record_plan(self, *, success: bool) -> None:
        self.plan_total += 1
        if success:
            self.plan_success += 1

    def record_tool_call(self, *, ok: bool) -> None:
        self.tool_calls += 1
        if not ok:
            self.tool_failures += 1

    def record_schema(self, *, ok: bool) -> None:
        self.schema_checks += 1
        if ok:
            self.schema_ok += 1

    def kpi_snapshot(self) -> dict[str, float | int]:
        pt = max(1, self.plan_total)
        tt = max(1, self.tool_calls)
        st = max(1, self.schema_checks)
        return {
            "planTotal": self.plan_total,
            "planSuccess": self.plan_success,
            "planSuccessRate": round(self.plan_success / pt, 6),
            "toolCalls": self.tool_calls,
            "toolFailures": self.tool_failures,
            "toolFailureRate": round(self.tool_failures / tt, 6),
            "schemaChecks": self.schema_checks,
            "schemaCompliant": self.schema_ok,
            "schemaComplianceRate": round(self.schema_ok / st, 6),
        }
