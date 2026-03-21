from __future__ import annotations

from app.contracts.otie import PlanStep
from app.services.policy_engine import PolicyEngine


class RuntimePolicyService:
    def __init__(self, engine: PolicyEngine) -> None:
        self._engine = engine

    def evaluate(self, step: PlanStep, step_approvals: dict[str, bool]) -> dict[str, object]:
        tool_ids = [step.tool_id] if step.tool_id else []
        assessment = self._engine.assess_step(step.action, tool_ids=tool_ids)
        allow = self._engine.is_step_allowed(assessment, step.id, step_approvals)
        return {**assessment, "allow": allow}
