"""
Constitution-style policy checks for plan steps (risk + approval gates).

Tenant/session overrides can be wired later via constructor args.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Set


@dataclass
class PolicyEngine:
    """Evaluate per-step risk and whether execution is allowed before approval."""

    deny_keywords: tuple[str, ...] = ("delete", "payment", "转账", "删除")
    allow_tools: Optional[Set[str]] = None  # if set, only these tool ids allowed (future)
    deny_tools: Optional[Set[str]] = None
    tenant_id: str = ""

    def assess_step(self, step_text: str, *, tool_ids: Optional[list[str]] = None) -> dict[str, Any]:
        text = (step_text or "").lower()
        risk = "high" if any(k in text for k in self.deny_keywords) else "low"
        tool_ids = tool_ids or []
        denied_tool: Optional[str] = None
        if self.deny_tools:
            for tid in tool_ids:
                if tid in self.deny_tools:
                    denied_tool = tid
                    risk = "high"
                    break
        if self.allow_tools is not None and tool_ids:
            for tid in tool_ids:
                if tid not in self.allow_tools:
                    denied_tool = tid
                    risk = "high"
                    break

        return {
            "riskLevel": risk,
            "deniedTool": denied_tool,
            "requiresApproval": risk == "high" or bool(denied_tool),
        }

    def is_step_allowed(
        self, assessment: dict[str, Any], step_id: str, step_approvals: Optional[dict[str, Any]]
    ) -> bool:
        if assessment.get("deniedTool"):
            return False
        if assessment.get("riskLevel") == "high":
            return bool(isinstance(step_approvals, dict) and step_approvals.get(step_id))
        return True
