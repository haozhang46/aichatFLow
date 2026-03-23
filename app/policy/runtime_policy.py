from __future__ import annotations

from typing import Any

from app.contracts.otie import PlanStep
from app.services.policy_engine import PolicyEngine


class RuntimePolicyService:
    def __init__(self, engine: PolicyEngine) -> None:
        self._engine = engine

    def evaluate(
        self,
        step: PlanStep,
        step_approvals: dict[str, bool],
        *,
        allowed_tool_ids: list[str] | None = None,
    ) -> dict[str, object]:
        tool_ids = [step.tool_id] if step.tool_id else []
        assessment = self._engine.assess_step(step.action, tool_ids=tool_ids)
        normalized_allowed = {str(item).strip() for item in (allowed_tool_ids or []) if str(item).strip()}
        denied_tool: Any = assessment.get("deniedTool")
        if normalized_allowed and tool_ids:
            for tool_id in tool_ids:
                if tool_id not in normalized_allowed:
                    denied_tool = tool_id
                    assessment = {
                        **assessment,
                        "riskLevel": "high",
                        "deniedTool": tool_id,
                        "requiresApproval": True,
                    }
                    break
        allow = self._engine.is_step_allowed(assessment, step.id, step_approvals)
        return {**assessment, "deniedTool": denied_tool, "allow": allow}
