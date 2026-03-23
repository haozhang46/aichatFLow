"""Normalize execution steps from executionPlan + confirmedPlan + stepExecutions + overrides."""

from __future__ import annotations

from typing import Any, Optional


def _safe_list_skills(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [str(x).strip() for x in raw if str(x).strip()]


def _safe_list_tools(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [str(x).strip() for x in raw if str(x).strip()]


def _safe_tool_inputs(raw: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(raw, dict):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for tool_id, value in raw.items():
        if not isinstance(value, dict):
            continue
        normalized_tool_id = str(tool_id).strip()
        if not normalized_tool_id:
            continue
        result[normalized_tool_id] = {
            str(key).strip(): item
            for key, item in value.items()
            if str(key).strip()
        }
    return result


def _execution_map(step_executions: Optional[list[Any]]) -> dict[int, dict[str, Any]]:
    m: dict[int, dict[str, Any]] = {}
    if not isinstance(step_executions, list):
        return m
    for item in step_executions:
        if not isinstance(item, dict):
            continue
        idx = item.get("stepIndex")
        if isinstance(idx, int) and idx >= 0:
            m[idx] = item
    return m


def normalize_execution_steps(
    *,
    execution_plan: Optional[dict[str, Any]],
    confirmed_plan: Optional[list[Any]],
    step_executions: Optional[list[Any]],
    default_mode: str,
    step_overrides: Optional[dict[str, Any]] = None,
) -> list[dict[str, Any]]:
    """
    Returns ordered steps:
    { id, type, action, agent, skills, tools, toolInputs, dependsOn, retryPolicy, timeoutMs }
    """
    step_overrides = step_overrides or {}
    ex_map = _execution_map(step_executions)
    steps: list[dict[str, Any]] = []

    raw_steps: list[dict[str, Any]] = []
    if isinstance(execution_plan, dict):
        rs = execution_plan.get("steps")
        if isinstance(rs, list):
            for item in rs:
                if isinstance(item, dict):
                    raw_steps.append(item)

    if not raw_steps and isinstance(confirmed_plan, list):
        for idx, line in enumerate(confirmed_plan):
            text = str(line).strip()
            if not text:
                continue
            raw_steps.append(
                {
                    "id": f"s{idx + 1}",
                    "type": "llm",
                    "action": text,
                    "dependsOn": [f"s{idx}"] if idx > 0 else [],
                    "agent": default_mode,
                    "skills": [],
                }
            )

    for idx, item in enumerate(raw_steps):
        sid = str(item.get("id") or f"s{idx + 1}").strip() or f"s{idx + 1}"
        action = str(item.get("action") or "").strip()
        ov = step_overrides.get(sid) if isinstance(step_overrides, dict) else None
        if isinstance(ov, dict):
            alt = ov.get("action") or ov.get("text")
            if isinstance(alt, str) and alt.strip():
                action = alt.strip()
        if not action:
            continue
        stype = str(item.get("type") or "llm").strip() or "llm"
        depends = item.get("dependsOn")
        if not isinstance(depends, list):
            depends = []
        agent = str(item.get("agent") or default_mode).strip() or default_mode
        skills = _safe_list_skills(item.get("skills"))
        tools = _safe_list_tools(item.get("tools"))
        tool_inputs = _safe_tool_inputs(item.get("toolInputs"))

        merged = ex_map.get(idx)
        if isinstance(merged, dict):
            ma = merged.get("agent")
            if isinstance(ma, str) and ma.strip():
                agent = ma.strip()
            ms = merged.get("skills")
            skills = _safe_list_skills(ms) if ms is not None else skills
            mt = merged.get("tools")
            tools = _safe_list_tools(mt) if mt is not None else tools
            mti = merged.get("toolInputs")
            tool_inputs = _safe_tool_inputs(mti) if mti is not None else tool_inputs

        retry = item.get("retryPolicy")
        if not isinstance(retry, dict):
            retry = {"maxRetries": 0, "backoffMs": 0}
        timeout_ms = item.get("timeoutMs")
        if timeout_ms is not None and not isinstance(timeout_ms, (int, float)):
            timeout_ms = None
        output_schema = item.get("outputSchema")
        if output_schema is not None and not isinstance(output_schema, dict):
            output_schema = None

        steps.append(
            {
                "id": sid,
                "type": stype,
                "action": action,
                "dependsOn": depends,
                "agent": agent,
                "skills": skills,
                "tools": tools,
                "toolInputs": tool_inputs,
                "retryPolicy": retry,
                "timeoutMs": timeout_ms,
                "outputSchema": output_schema,
            }
        )

    return steps
