from __future__ import annotations

from uuid import uuid4
from datetime import datetime
import json
import re
import time
from typing import Any, Optional

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import (
    agent_registry_service,
    approval_store,
    capability_service,
    deepagent_runtime_adapter,
    executor_service,
    metrics_service,
    personal_skill_tree_service,
    plan_record_service,
    platform_trace_service,
    routing_service,
    skill_executor_service,
    tool_definition_registry_service,
    trace_store,
    otie_runtime,
    otie_trace_service,
    otie_intent_service,
    otie_planner,
    tool_registry,
    tool_policy_service,
)
from app.contracts.otie import ExecutionPlan, OtieRequestInput, PlanStep, RetryPolicy
from app.schemas.unified import UnifiedRequest
from app.services.execution_steps import normalize_execution_steps
from app.orchestrator.graph import (
    build_plan_context,
    run_orchestrator,
)
from app.core.config import settings
from app.runtime.deepagent_adapter import DeepAgentInvokeContext, DeepAgentInvokeRequest
from app.services.clawhub_service import search_skills as clawhub_search_skills
from app.services.clawhub_plan_analysis import build_clawhub_plan_suggestions
from app.services.trace_store import sanitize_sensitive_data

router = APIRouter()

class PlanRecordSaveIn(BaseModel):
    query: str
    intent_description: str = Field(alias="intentDescription")
    mode: str
    plan_lines: list[str] = Field(alias="planLines")
    recommended_skills: list[str] = Field(default_factory=list, alias="recommendedSkills")
    supplement: str = ""


class CapabilityInstallIn(BaseModel):
    skill_id: str = Field(alias="skillId")


class CapabilityWhitelistIn(BaseModel):
    skill_id: str = Field(alias="skillId")
    enabled: bool


class ToolPolicyIn(BaseModel):
    tool_id: str = Field(alias="toolId")
    allowlisted: Optional[bool] = None
    denylisted: Optional[bool] = None


class OnlineSkillAddIn(BaseModel):
    skill_id: str = Field(alias="skillId")


class AgentCreateIn(BaseModel):
    agent_id: str = Field(alias="agentId")
    label: str = ""
    description: str = ""
    system_prompt: str = Field(default="", alias="systemPrompt")
    version: str = "0.1.0"
    available_tools: list[str] = Field(default_factory=list, alias="availableTools")
    runtime: Optional[dict[str, Any]] = None
    memory: Optional[dict[str, Any]] = None
    policy: Optional[dict[str, Any]] = None


class ToolRegisterIn(BaseModel):
    manifest: dict[str, Any] | None = None


class DraftPromptIn(BaseModel):
    prompt: str


class AgentInvokeIn(BaseModel):
    prompt: Optional[str] = None
    input: Optional[dict[str, Any]] = None
    context: Optional[dict[str, Any]] = None
    runtime_options: Optional[dict[str, Any]] = Field(default=None, alias="runtimeOptions")
    llm_config: Optional[dict[str, str]] = Field(default=None, alias="llmConfig")


class PersonalSkillPathIn(BaseModel):
    path: str


class ClawhubRegisterIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    slug: str = ""
    skill_id: str = Field(default="", alias="skillId")
    display_name: str = Field(default="", alias="displayName")
    summary: str = ""


def _get_strategy(payload: UnifiedRequest) -> str:
    strategy = "auto"
    if payload.inputs:
        raw_strategy = payload.inputs.get("strategy")
        if isinstance(raw_strategy, str) and raw_strategy in ["auto", "agent", "react", "workflow"]:
            strategy = raw_strategy
    return strategy


def _get_llm_config(payload: UnifiedRequest) -> Optional[dict[str, str]]:
    if not payload.inputs:
        return None
    raw = payload.inputs.get("llmConfig")
    if not isinstance(raw, dict):
        return None
    provider = str(raw.get("provider", "")).strip().lower()
    api_key = str(raw.get("apiKey", "")).strip()
    base_url = str(raw.get("baseUrl", "")).strip()
    model = str(raw.get("model", "")).strip()
    if provider != "deepseek" or not api_key:
        return None
    return {
        "apiKey": api_key,
        "baseUrl": base_url or "https://api.deepseek.com/v1",
        "model": model or "deepseek-chat",
    }


def _suggest_execution_mode(query: str) -> str:
    q = query.lower()
    if any(k in q for k in ["学习计划", "学习", "计划", "checklist", "清单", "todo", "roadmap"]):
        return "user_exec"
    return "auto_exec"


def _get_execution_mode(payload: UnifiedRequest, query: str) -> str:
    raw = (payload.inputs or {}).get("executionMode")
    if isinstance(raw, str) and raw in ["auto_exec", "user_exec"]:
        return raw
    return _suggest_execution_mode(query)


def _has_rag_request(payload: UnifiedRequest) -> bool:
    raw = (payload.inputs or {}).get("rag")
    if not isinstance(raw, dict):
        return False
    if bool(raw.get("enabled")):
        return True
    return bool(str(raw.get("scope") or "").strip())


def _build_execution_plan(plan_lines: list[str], mode: str) -> dict[str, Any]:
    steps: list[dict[str, Any]] = []
    for idx, line in enumerate(plan_lines):
        text = str(line).strip()
        if not text:
            continue
        steps.append(
            {
                "id": f"s{idx + 1}",
                "type": "llm",
                "action": text,
                "input": {"text": text},
                "dependsOn": [f"s{idx}"] if idx > 0 else [],
                "agent": mode,
                "skills": [],
                "retryPolicy": {"maxRetries": 0, "backoffMs": 0},
                "timeoutMs": None,
            }
        )
    return {"planId": f"plan_{uuid4().hex[:10]}", "mode": mode, "steps": steps}


def _coerce_step_strategy(step_agent: str, fallback: str) -> str:
    if step_agent in ("agent", "react", "workflow", "auto"):
        return step_agent
    return fallback


def _build_otie_request(payload: UnifiedRequest, query: str) -> OtieRequestInput:
    metadata = dict(payload.metadata or {})
    return OtieRequestInput(
        requestId=payload.request_id,
        tenantId=payload.tenant_id,
        requestType=payload.request_type,
        messages=[{"role": "user", "content": query}],
        inputs=payload.inputs or {},
        metadata=metadata,
    )


def _current_user_id(request: Request) -> str:
    for key in ("user_id", "userId", "uid", "session_user", "sessionUser"):
        value = request.cookies.get(key)
        if value and value.strip():
            return value.strip()
    return ""


def _known_agent_ids() -> set[str]:
    builtin = {str(item.get("id") or "").strip() for item in capability_service.list_agents()}
    custom = {str(item.get("id") or "").strip() for item in agent_registry_service.list_registered_agents()}
    return {item for item in builtin | custom if item}


def _validate_tool_manifest_policy(manifest: dict[str, Any]) -> Optional[str]:
    policy = manifest.get("policy") if isinstance(manifest.get("policy"), dict) else {}
    allow_agents = policy.get("allowAgents") if isinstance(policy.get("allowAgents"), list) else []
    if not allow_agents:
        return None
    known_agent_ids = _known_agent_ids()
    missing = [str(item).strip() for item in allow_agents if str(item).strip() and str(item).strip() not in known_agent_ids]
    if missing:
        return f"tool policy.allowAgents contains unknown agent ids: {', '.join(sorted(missing))}"
    return None


def _validate_agent_available_tools(agent_id: str, available_tools: list[str]) -> Optional[str]:
    normalized_agent_id = str(agent_id or "").strip()
    for tool_id in [str(item).strip() for item in available_tools if str(item).strip()]:
        if not tool_registry.has_tool(tool_id):
            return f"agent availableTools contains unknown tool `{tool_id}`"
        tool_meta = tool_registry.describe_tool(tool_id) or {"id": tool_id}
        policy = tool_meta.get("policy") if isinstance(tool_meta.get("policy"), dict) else {}
        allow_agents = policy.get("allowAgents") if isinstance(policy.get("allowAgents"), list) else []
        if allow_agents and normalized_agent_id not in {str(item).strip() for item in allow_agents if str(item).strip()}:
            return f"tool `{tool_id}` is not allowed for agent `{normalized_agent_id}`"
    return None


def _normalize_agent_spec(payload: AgentCreateIn) -> dict[str, Any]:
    agent_id = payload.agent_id.strip()
    name = payload.label.strip() or agent_id
    runtime = payload.runtime if isinstance(payload.runtime, dict) else {"mode": "agent", "maxSteps": 8}
    runtime = {**runtime}
    runtime.setdefault("engine", "otie")
    return {
        "id": agent_id,
        "name": name,
        "description": payload.description.strip() or f"Custom agent `{agent_id}`",
        "version": payload.version.strip() or "0.1.0",
        "systemPrompt": payload.system_prompt.strip(),
        "availableTools": [str(item).strip() for item in payload.available_tools if str(item).strip()],
        "runtime": runtime,
        "memory": payload.memory if isinstance(payload.memory, dict) else {"type": "none"},
        "policy": payload.policy if isinstance(payload.policy, dict) else {"requiresUserContext": False},
    }


def _normalize_agent_invoke_request(payload: AgentInvokeIn) -> tuple[str, dict[str, Any], dict[str, Any]]:
    raw_input = payload.input if isinstance(payload.input, dict) else {}
    prompt = str(payload.prompt or raw_input.get("message") or raw_input.get("prompt") or "").strip()
    context = payload.context if isinstance(payload.context, dict) else {}
    runtime_options = payload.runtime_options if isinstance(payload.runtime_options, dict) else {}
    return prompt, context, runtime_options


def _agent_runtime_engine(record: dict[str, Any] | None) -> str:
    runtime = record.get("runtime") if isinstance((record or {}).get("runtime"), dict) else {}
    engine = str(runtime.get("engine") or "otie").strip().lower()
    return engine if engine in {"otie", "deepagent"} else "otie"


def _safe_llm_config_for_response(raw: Any) -> Any:
    return sanitize_sensitive_data(raw)


def _get_registered_deepagent_record(agent_id: str) -> dict[str, Any] | None:
    record = agent_registry_service.get_agent_record(agent_id)
    if record is None:
        return None
    return record if _agent_runtime_engine(record) == "deepagent" else None


def _sse_event(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _plan_step_names(plan: ExecutionPlan) -> dict[str, str]:
    return {step.id: step.action for step in plan.steps}


def _frontend_event_from_trace(
    event: dict[str, Any],
    *,
    run_id: str,
    step_names: dict[str, str],
    step_outputs: dict[str, Any],
) -> dict[str, Any] | None:
    event_type = str(event.get("type") or "").strip()
    step_id = str(event.get("stepId") or "").strip()
    step_name = step_names.get(step_id) or str(event.get("action") or "").strip()

    if event_type == "step_started":
        return {
            "type": "step_started",
            "runId": run_id,
            "stepId": step_id,
            "stepName": step_name,
            "kind": event.get("kind"),
        }

    if event_type == "tool_call":
        return {
            "type": "tool_call",
            "runId": run_id,
            "stepId": step_id,
            "stepName": step_name,
            "toolId": event.get("toolId"),
            "args": event.get("args") or {},
        }

    if event_type == "tool_result":
        return {
            "type": "tool_result",
            "runId": run_id,
            "stepId": step_id,
            "stepName": step_name,
            "toolId": event.get("toolId"),
            "result": event.get("result"),
        }

    if event_type == "step_completed":
        return {
            "type": "step_completed",
            "runId": run_id,
            "stepId": step_id,
            "stepName": step_name,
            "status": event.get("status") or "success",
            "output": step_outputs.get(step_id),
        }

    if event_type == "run_finished":
        return {
            "type": "run_completed",
            "runId": run_id,
            "status": event.get("status"),
            "finalAnswer": event.get("finalAnswer"),
        }

    return None


def _build_otie_plan_from_steps(
    *,
    request_id: str,
    intent_id: str,
    default_mode: str,
    steps: list[dict[str, Any]],
) -> ExecutionPlan:
    plan_steps: list[PlanStep] = []
    for idx, step in enumerate(steps):
        step_id = str(step.get("id") or f"s{idx + 1}")
        skills = [str(s).strip() for s in (step.get("skills") or []) if str(s).strip()]
        tools = [str(t).strip() for t in (step.get("tools") or []) if str(t).strip()]
        tool_inputs = step.get("toolInputs") if isinstance(step.get("toolInputs"), dict) else {}
        depends_on = [str(s) for s in (step.get("dependsOn") or []) if str(s).strip()]
        for skill_index, skill_id in enumerate(skills):
            skill_step_id = f"{step_id}_tool_{skill_index + 1}"
            skill_depends = list(depends_on) if skill_index == 0 else [plan_steps[-1].id]
            plan_steps.append(
                PlanStep(
                    stepId=skill_step_id,
                    kind="tool",
                    action=f"Execute skill `{skill_id}` for step `{step_id}`.",
                    dependsOn=skill_depends,
                    toolId="execute-skill",
                    toolArgs={"skillId": skill_id, "query": str(step.get('action') or '')},
                    agent="auto",
                )
            )
            depends_on = [skill_step_id]
        for tool_index, tool_id in enumerate(tools):
            tool_step_id = f"{step_id}_otie_tool_{tool_index + 1}"
            tool_depends = list(depends_on) if tool_index == 0 else [plan_steps[-1].id]
            plan_steps.append(
                PlanStep(
                    stepId=tool_step_id,
                    kind="tool",
                    action=f"Execute tool `{tool_id}` for step `{step_id}`.",
                    dependsOn=tool_depends,
                    toolId=tool_id,
                    toolArgs={
                        "query": str(step.get("action") or ""),
                        **(tool_inputs.get(tool_id) if isinstance(tool_inputs.get(tool_id), dict) else {}),
                    },
                    agent="auto",
                )
            )
            depends_on = [tool_step_id]

        kind = "tool" if str(step.get("type") or "").strip() == "tool" else "reason"
        tool_id = None
        tool_args = {}
        if kind == "tool":
            tool_id = str(step.get("toolId") or "").strip() or "execute-skill"
            tool_args = step.get("input") if isinstance(step.get("input"), dict) else {}
        plan_steps.append(
            PlanStep(
                stepId=step_id,
                kind=kind,
                action=str(step.get("action") or ""),
                dependsOn=depends_on,
                agent=_coerce_step_strategy(str(step.get("agent") or default_mode), default_mode),
                toolId=tool_id,
                toolArgs=tool_args,
                retryPolicy=RetryPolicy.model_validate(step.get("retryPolicy") or {}),
                timeoutMs=step.get("timeoutMs"),
                outputSchema=step.get("outputSchema"),
            )
        )

    if not plan_steps or plan_steps[-1].kind != "respond":
        plan_steps.append(
            PlanStep(
                stepId=f"s{len(plan_steps) + 1}",
                kind="respond",
                action="Compose the final response from completed step outputs.",
                dependsOn=[plan_steps[-1].id] if plan_steps else [],
                agent="agent",
            )
        )

    return ExecutionPlan(
        planId=f"plan_{request_id}",
        intentId=intent_id,
        mode=default_mode if default_mode in {"agent", "react", "workflow"} else "agent",
        status="ready",
        maxSteps=max(len(plan_steps) + 2, 4),
        steps=plan_steps,
    )


def _extract_weather_location(query: str) -> str:
    q = str(query or "").strip()
    lowered = q.lower()
    weather_keywords = ["weather", "forecast", "temperature", "天气", "气温", "温度", "预报"]
    if not any(keyword in lowered for keyword in weather_keywords):
        return ""

    english_match = re.search(r"(?:weather|forecast|temperature)\s+(?:in|for)\s+([a-zA-Z\s,.-]+)", q, re.IGNORECASE)
    if english_match:
        return _normalize_weather_location(english_match.group(1))

    chinese_match = re.search(r"(?:查询|查|看看|看下)?(.+?)(?:今天|今日|明天|天气|气温|温度|预报)", q)
    if chinese_match:
        candidate = _normalize_weather_location(chinese_match.group(1))
        if candidate:
            return candidate

    return _normalize_weather_location(q)


def _normalize_weather_location(value: str) -> str:
    text = value.strip(" 在的，,。.?!")
    text = re.sub(r"\b(today|tomorrow|now|right now|this week)\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"(今天|今日|明天|现在|当前|这周)$", "", text)
    return text.strip(" ,.-")


def _steps_include_tool(steps: list[dict[str, Any]], tool_id: str) -> bool:
    target = str(tool_id).strip()
    if not target:
        return False
    for step in steps:
        if not isinstance(step, dict):
            continue
        step_type = str(step.get("type") or "").strip().lower()
        if step_type == "tool" and str(step.get("toolId") or "").strip() == target:
            return True
        if target in {str(item).strip() for item in (step.get("tools") or []) if str(item).strip()}:
            return True
    return False


def _augment_steps_for_query(query: str, steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized_steps: list[dict[str, Any]] = []
    q = str(query or "").lower()
    keep_find_skills = any(
        token in q
        for token in ["skill", "skills", "agent", "agents", "capability", "capabilities", "插件", "能力", "安装", "install"]
    )
    for step in steps:
        if not isinstance(step, dict):
            continue
        updated = {**step}
        skills = [str(item).strip() for item in (updated.get("skills") or []) if str(item).strip()]
        tools = [str(item).strip() for item in (updated.get("tools") or []) if str(item).strip()]
        if not keep_find_skills:
            skills = [item for item in skills if item != "find-skills"]
            tools = [item for item in tools if item != "find-skills"]
        updated["skills"] = skills
        updated["tools"] = tools
        normalized_steps.append(updated)

    weather_location = _extract_weather_location(query)
    if not weather_location or _steps_include_tool(normalized_steps, "weather"):
        return normalized_steps

    weather_step_id = "auto_weather_1"
    inserted: list[dict[str, Any]] = [
        {
            "id": weather_step_id,
            "type": "tool",
            "action": f"Fetch current weather for `{weather_location}`.",
            "dependsOn": [],
            "agent": "auto",
            "tools": [],
            "toolInputs": {},
            "input": {"location": weather_location, "query": query},
            "toolId": "weather",
        }
    ]

    for idx, step in enumerate(normalized_steps):
        updated = {**step}
        depends_on = updated.get("dependsOn")
        if not isinstance(depends_on, list):
            depends_on = []
        if idx == 0 and weather_step_id not in depends_on:
            depends_on = [weather_step_id, *[str(item) for item in depends_on if str(item).strip()]]
        updated["dependsOn"] = depends_on
        inserted.append(updated)
    return inserted


async def _resolve_otie_plan_for_payload(
    payload: UnifiedRequest,
    *,
    query: str,
    strategy: str,
    current_user_id: str = "",
) -> tuple[OtieRequestInput, Any, ExecutionPlan]:
    metadata = dict(payload.metadata or {})
    if current_user_id:
        metadata["currentUserId"] = current_user_id
    payload_with_user = payload.model_copy(update={"metadata": metadata})
    otie_request = _build_otie_request(payload_with_user, query)
    intent = otie_intent_service.normalize(otie_request)

    execution_plan = (payload.inputs or {}).get("executionPlan")
    confirmed_plan = (payload.inputs or {}).get("confirmedPlan")
    step_executions = (payload.inputs or {}).get("stepExecutions")
    step_overrides = (payload.inputs or {}).get("stepOverrides")

    if isinstance(execution_plan, dict) or isinstance(confirmed_plan, list):
        default_mode = strategy
        if isinstance(execution_plan, dict):
            raw_mode = execution_plan.get("mode")
            if isinstance(raw_mode, str) and raw_mode.strip():
                default_mode = raw_mode.strip()
        steps = normalize_execution_steps(
            execution_plan=execution_plan if isinstance(execution_plan, dict) else None,
            confirmed_plan=confirmed_plan if isinstance(confirmed_plan, list) else None,
            step_executions=step_executions if isinstance(step_executions, list) else None,
            default_mode=default_mode,
            step_overrides=step_overrides if isinstance(step_overrides, dict) else None,
        )
        steps = _augment_steps_for_query(query, steps)
        plan = _build_otie_plan_from_steps(
            request_id=payload.request_id,
            intent_id=intent.intent_id,
            default_mode=default_mode,
            steps=steps,
        )
        return otie_request, intent, plan

    plan = await otie_planner.build_plan(intent)
    return otie_request, intent, plan


@router.post("/v1/unified/execute")
async def execute_unified(payload: UnifiedRequest, request: Request):
    # For chat requests, use LangChain/LangGraph orchestrator to select agent/react/workflow automatically.
    if payload.request_type == "chat":
        query = (payload.messages or [{"content": ""}])[0].get("content", "")
        strategy = _get_strategy(payload)
        started = time.monotonic()
        _, intent, plan = await _resolve_otie_plan_for_payload(
            payload,
            query=query,
            strategy=strategy,
            current_user_id=_current_user_id(request),
        )
        result = await otie_runtime.run(
            intent,
            plan,
            step_approvals=(payload.inputs or {}).get("stepApprovals")
            if isinstance((payload.inputs or {}).get("stepApprovals"), dict)
            else {},
        )
        latency_ms = int((time.monotonic() - started) * 1000)
        status = "success"
        if result.status == "awaiting_approval":
            status = "partial"
        elif result.status == "failed":
            status = "failed"
        return {
            "requestId": payload.request_id,
            "provider": "langchain",
            "status": status,
            "output": {
                "mode": plan.mode,
                "answer": result.final_answer,
                "runId": result.run_id,
                "executionPlan": plan.model_dump(by_alias=True),
                "stepOutputs": result.step_outputs,
            },
            "error": None if status != "failed" else {"message": result.final_answer},
            "latencyMs": latency_ms,
            "traceId": result.trace_id,
            "fallbackUsed": False,
            "timestamp": datetime.utcnow().isoformat(),
        }

    # For workflow requests, keep the previous FastGPT/Dify execution path.
    trace_id = f"trace_{uuid4().hex[:12]}"
    try:
        route = await routing_service.resolve(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    response = await executor_service.execute(payload, route, trace_id)
    if response.status == "failed":
        raise HTTPException(status_code=502, detail=response.error)
    return response


@router.post("/v1/unified/plan")
async def plan_unified(payload: UnifiedRequest):
    if payload.request_type != "chat":
        raise HTTPException(status_code=400, detail="plan only supports requestType=chat")
    trace_id = f"trace_{uuid4().hex[:12]}"
    query = (payload.messages or [{"content": ""}])[0].get("content", "")
    strategy = _get_strategy(payload)
    llm_config = _get_llm_config(payload)
    execution_mode = _get_execution_mode(payload, query)
    reused_record = None if _has_rag_request(payload) else plan_record_service.find_latest_by_query(query)
    if reused_record:
        mode = str(reused_record.get("mode") or strategy or "auto")
        plan_lines = [str(x).strip() for x in reused_record.get("planLines", []) if str(x).strip()]
        execution_plan = _build_execution_plan(plan_lines, mode)
        rec = capability_service.recommend(query, mode)
        recommended_skills = reused_record.get("recommendedSkills", [])
        if recommended_skills:
            rec["recommendedSkills"] = recommended_skills
            rec["requiredSkills"] = recommended_skills
            rec["missingSkills"] = [
                skill_id for skill_id in recommended_skills if skill_id not in capability_service.list_whitelist()
            ]
            rec["installRequired"] = len(rec["missingSkills"]) > 0
        metrics_service.record_plan(success=True)
        return {
            "requestId": payload.request_id,
            "provider": "langchain",
            "status": "success",
            "output": {
                "phase": "plan",
                "mode": mode,
                "plan": plan_lines,
                "executionPlan": execution_plan,
                "executionMode": execution_mode,
                "intentDescription": reused_record.get("intentDescription", f"用户希望解决：{query}"),
                "thinking": "Reused existing plan record for identical query.",
                "searchEvidence": [],
                "clawhubPlanSuggestions": [],
                "reusedFromPlanRecord": True,
                "planRecordPath": reused_record.get("path"),
                "requiredSkills": rec.get("requiredSkills", []),
                **rec,
            },
            "error": None,
            "latencyMs": 0,
            "traceId": trace_id,
            "fallbackUsed": False,
            "timestamp": datetime.utcnow().isoformat(),
        }
    plan_context = await build_plan_context(query, strategy=strategy, llm_config=llm_config)
    mode = plan_context["mode"]
    plan_lines = plan_context["plan"]
    execution_plan = _build_execution_plan(plan_lines, mode)
    latency_ms = plan_context["latencyMs"]
    rec = capability_service.recommend(query, mode)
    intent_desc = plan_context.get("intentDescription", f"用户希望解决：{query}")
    clawhub_plan_suggestions = await build_clawhub_plan_suggestions(
        query=query,
        intent=str(intent_desc),
        plan_lines=plan_lines,
        llm_config=llm_config,
        search_limit=8,
    )
    metrics_service.record_plan(success=True)
    return {
        "requestId": payload.request_id,
        "provider": "langchain",
        "status": "success",
        "output": {
            "phase": "plan",
            "mode": mode,
            "plan": plan_lines,
            "executionPlan": execution_plan,
            "executionMode": execution_mode,
            "intentDescription": intent_desc,
            "thinking": plan_context.get("thinking", ""),
            "searchEvidence": plan_context.get("searchEvidence", []),
            "clawhubPlanSuggestions": clawhub_plan_suggestions,
            "reusedFromPlanRecord": False,
            "requiredSkills": rec.get("recommendedSkills", []),
            **rec,
        },
        "error": None,
        "latencyMs": latency_ms,
        "traceId": trace_id,
        "fallbackUsed": False,
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/v1/capabilities")
async def list_capabilities(q: Optional[str] = None, page: int = 1, pageSize: int = 8):
    skills_page = capability_service.list_skills_paginated(
        query=q,
        page=max(1, page),
        page_size=max(1, min(pageSize, 50)),
    )
    builtin_agents = capability_service.list_agents(query=q)
    custom_agents = agent_registry_service.list_agents()
    if q:
        keyword = q.strip().lower()
        custom_agents = [
            a
            for a in custom_agents
            if keyword in a["id"].lower()
            or keyword in a["label"].lower()
            or keyword in a.get("description", "").lower()
        ]
    tools = []
    for item in tool_registry.describe_tools():
        tools.append({**item, **tool_policy_service.status_for(str(item["id"]))})
    return {
        "agents": builtin_agents + custom_agents,
        "skills": skills_page["items"],
        "tools": tools,
        "skillsTotal": skills_page["total"],
        "page": skills_page["page"],
        "pageSize": skills_page["pageSize"],
        "whitelist": capability_service.list_whitelist(),
        "toolPolicy": tool_policy_service.snapshot(),
    }


@router.post("/v1/capabilities/install")
async def install_capability(payload: CapabilityInstallIn) -> dict[str, Any]:
    result = capability_service.install_skill(payload.skill_id)
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return {"status": "success", "message": result["message"]}


@router.post("/v1/capabilities/whitelist")
async def set_capability_whitelist(payload: CapabilityWhitelistIn) -> dict[str, Any]:
    result = capability_service.set_whitelist(payload.skill_id, payload.enabled)
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return {"status": "success", "skillId": payload.skill_id, "enabled": result["whitelisted"]}


@router.post("/v1/capabilities/tools/policy")
async def set_tool_policy(payload: ToolPolicyIn) -> dict[str, Any]:
    if not tool_registry.has_tool(payload.tool_id):
        raise HTTPException(status_code=404, detail="tool not found")
    result = tool_policy_service.set_policy(
        payload.tool_id,
        allowlisted=payload.allowlisted,
        denylisted=payload.denylisted,
    )
    return {"status": "success", **result}


@router.get("/v1/capabilities/online-search")
async def online_search_capabilities(q: str = "") -> dict[str, Any]:
    return {"items": capability_service.search_online_skills(q)}


@router.get("/v1/clawhub/search")
async def clawhub_search(q: str = "", limit: int = 25) -> dict[str, Any]:
    """
    Proxy to the public ClawHub registry (vector search). No API key required for read.
    Configure base URL with env CLAWHUB_REGISTRY_URL (default https://clawhub.ai).
    """
    try:
        data = await clawhub_search_skills(q, limit=limit)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"ClawHub request failed: {exc}") from exc
    items: list[dict[str, Any]] = []
    for r in data.get("results") or []:
        slug = str(r.get("slug") or "").strip()
        if not slug:
            continue
        sk = capability_service.get_skill(slug)
        items.append(
            {
                "id": slug,
                "name": str(r.get("displayName") or slug),
                "source": "clawhub",
                "summary": str(r.get("summary") or ""),
                "score": r.get("score"),
                "installed": bool(sk and sk.get("installed")),
                "whitelisted": bool(sk and sk.get("whitelisted")),
            }
        )
    return {"items": items, "registry": settings.clawhub_registry_url}


@router.post("/v1/clawhub/register")
async def clawhub_register(payload: ClawhubRegisterIn) -> dict[str, Any]:
    """Register a ClawHub skill slug into this gateway's curated list (whitelist / install flows)."""
    slug = (payload.slug or payload.skill_id or "").strip()
    if not slug:
        raise HTTPException(status_code=400, detail="slug or skillId is required")
    result = capability_service.register_clawhub_skill(
        slug, display_name=payload.display_name, summary=payload.summary
    )
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return {"status": "success", "message": result["message"], "slug": slug}


@router.post("/v1/capabilities/add-online")
async def add_online_capability(payload: OnlineSkillAddIn) -> dict[str, Any]:
    result = capability_service.add_online_skill(payload.skill_id)
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return {"status": "success", "message": result["message"]}


@router.get("/v1/agents")
async def list_agents_registry() -> dict[str, Any]:
    # Use capability-shaped rows (string `source`, etc.) — same as /v1/capabilities `agents` custom entries.
    return {"items": agent_registry_service.list_agents()}


@router.post("/v1/agents")
@router.post("/v1/agents/register")
async def create_agent_registry(payload: AgentCreateIn) -> dict[str, Any]:
    agent_spec = _normalize_agent_spec(payload)
    available_tools_error = _validate_agent_available_tools(str(agent_spec.get("id") or ""), agent_spec["availableTools"])
    if available_tools_error:
        raise HTTPException(status_code=400, detail=available_tools_error)
    if payload.system_prompt.strip() or payload.available_tools or payload.runtime or payload.memory or payload.policy:
        result = agent_registry_service.register_agent(agent_spec)
    else:
        result = agent_registry_service.create_agent(payload.agent_id, payload.label, payload.description)
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result["message"])
    trace_id = platform_trace_service.new_trace_id("agentreg")
    platform_trace_service.emit(
        trace_id,
        "agent_registered",
        run_id=trace_id,
        status="success",
        agentId=str(result["agent"].get("id") or payload.agent_id),
        metadata={"version": result["agent"].get("version"), "status": result["agent"].get("status")},
    )
    return {"status": "success", "agent": result["agent"], "traceId": trace_id}


@router.post("/v1/agents/draft")
async def create_agent_draft(payload: DraftPromptIn) -> dict[str, Any]:
    result = agent_registry_service.create_draft(payload.prompt)
    if "draft" not in result:
        raise HTTPException(status_code=400, detail=result.get("message") or "failed to create agent draft")
    return {"status": "success", "draft": result["draft"]}


@router.get("/v1/agents/{agent_id}")
async def get_agent_registry(agent_id: str) -> dict[str, Any]:
    builtin = next((item for item in capability_service.list_agents() if item["id"] == agent_id), None)
    if builtin is not None:
        return {"agent": builtin}
    agent = agent_registry_service.get_agent_record(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"agent `{agent_id}` not found")
    return {"agent": agent}


@router.post("/v1/agents/{agent_id}/publish")
async def publish_agent_registry(agent_id: str) -> dict[str, Any]:
    result = agent_registry_service.publish_agent(agent_id)
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result["message"])
    trace_id = platform_trace_service.new_trace_id("agentpub")
    platform_trace_service.emit(
        trace_id,
        "draft_published",
        run_id=trace_id,
        status="success",
        agentId=str(result["agent"].get("id") or agent_id),
        metadata={"entityType": "agent", "version": result["agent"].get("version")},
    )
    platform_trace_service.emit(
        trace_id,
        "definition_published",
        run_id=trace_id,
        status="success",
        agentId=str(result["agent"].get("id") or agent_id),
        metadata={"entityType": "agent", "version": result["agent"].get("version")},
    )
    return {"status": "success", "agent": result["agent"], "traceId": trace_id}


@router.delete("/v1/agents/{agent_id}")
async def delete_agent_registry(agent_id: str) -> dict[str, Any]:
    result = agent_registry_service.delete_agent(agent_id)
    if not result["ok"]:
        raise HTTPException(status_code=404, detail=result["message"])
    return {"status": "success"}


@router.post("/v1/agents/{agent_id}/invoke")
async def invoke_agent(agent_id: str, payload: AgentInvokeIn, request: Request) -> dict[str, Any]:
    prompt, request_context, runtime_options = _normalize_agent_invoke_request(payload)
    if not prompt:
        raise HTTPException(status_code=400, detail="prompt is required")

    builtin = next((item for item in capability_service.list_agents() if item["id"] == agent_id), None)
    custom_record = agent_registry_service.get_agent_record(agent_id) if builtin is None else None
    custom = agent_registry_service.get_agent(agent_id) if builtin is None else None
    agent = builtin or custom
    if agent is None:
        raise HTTPException(status_code=404, detail=f"agent `{agent_id}` not found")

    strategy = agent_id if agent_id in {"agent", "react", "workflow"} else "agent"
    effective_prompt = prompt
    effective_available_tools: list[str] = []
    runtime_engine = "otie"
    if custom_record is not None:
        runtime = custom_record.get("runtime") if isinstance(custom_record.get("runtime"), dict) else {}
        runtime_mode = str(runtime.get("mode") or "").strip()
        runtime_engine = _agent_runtime_engine(custom_record)
        if runtime_mode in {"agent", "react", "workflow"}:
            strategy = runtime_mode
        system_prompt = str(custom_record.get("systemPrompt") or "").strip()
        agent_name = str(custom_record.get("name") or custom_record.get("label") or agent_id)
        agent_desc = str(custom_record.get("description") or "")
        available_tools = custom_record.get("availableTools") if isinstance(custom_record.get("availableTools"), list) else []
        effective_available_tools = [str(item).strip() for item in available_tools if str(item).strip()]
        available_tools_error = _validate_agent_available_tools(agent_id, effective_available_tools)
        if available_tools_error:
            raise HTTPException(status_code=400, detail=available_tools_error)
        effective_prompt = (
            f"You are the custom agent `{agent_name}`.\n"
            + f"Agent profile: {agent_desc}\n"
            + (f"Available tools: {', '.join(effective_available_tools)}\n" if effective_available_tools else "")
            + (f"System instructions:\n{system_prompt}\n\n" if system_prompt else "\n")
            + f"User request:\n{prompt}"
        )

    trace_id = platform_trace_service.new_trace_id("agent")
    span_id = platform_trace_service.new_span_id("agentinvoke")
    try:
        if runtime_engine == "deepagent":
            result = await deepagent_runtime_adapter.invoke(
                custom_record or {},
                request=DeepAgentInvokeRequest(
                    input={"message": prompt},
                    context=request_context,
                    runtime_options=runtime_options,
                    llm_config=payload.llm_config,
                ),
                context=DeepAgentInvokeContext(
                    trace_id=trace_id,
                    run_id=trace_id,
                    user_id=_current_user_id(request),
                    agent_id=agent_id,
                    tenant_id=str(request_context.get("tenantId") or "").strip() or None,
                    allowed_tool_ids=effective_available_tools,
                ),
            )
        else:
            platform_trace_service.emit(
                trace_id,
                "run_started",
                run_id=trace_id,
                span_id=span_id,
                status="running",
                agentId=agent_id,
                metadata={
                    "prompt": prompt[:500],
                    "strategy": strategy,
                    "context": request_context,
                    "runtimeOptions": runtime_options,
                    "availableTools": effective_available_tools,
                    "runtimeEngine": runtime_engine,
                },
            )
            mode, answer, latency_ms = await run_orchestrator(
                effective_prompt,
                strategy=strategy,  # type: ignore[arg-type]
                llm_config=payload.llm_config,
            )
            result = None
    except Exception as exc:
        platform_trace_service.emit(
            trace_id,
            "run_completed",
            run_id=trace_id,
            span_id=platform_trace_service.new_span_id("agentinvoke"),
            parent_span_id=span_id,
            status="failed",
            agentId=agent_id,
            metadata={"error": {"message": str(exc)}},
        )
        return {
            "status": "failed",
            "agent": agent,
            "request": {
                "input": {"message": prompt},
                "context": request_context,
                "runtimeOptions": runtime_options,
                "strategy": strategy,
                "llmConfig": _safe_llm_config_for_response(payload.llm_config),
                "availableTools": effective_available_tools,
                "runtimeEngine": runtime_engine,
            },
            "result": None,
            "error": {"code": "agent_invoke_failed", "message": str(exc)},
            "latencyMs": 0,
            "traceId": trace_id,
        }
    if runtime_engine == "deepagent":
        assert result is not None
        mode = result.mode
        answer = result.answer
        latency_ms = result.latency_ms
        if result.status != "success":
            return {
                "status": "failed",
                "agent": agent,
                "request": {
                    "input": {"message": prompt},
                    "context": request_context,
                    "runtimeOptions": runtime_options,
                    "strategy": strategy,
                    "llmConfig": _safe_llm_config_for_response(payload.llm_config),
                    "availableTools": effective_available_tools,
                    "runtimeEngine": runtime_engine,
                },
                "result": None,
                "stepOutputs": result.step_outputs,
                "events": result.events,
                "error": result.error,
                "latencyMs": latency_ms,
                "traceId": trace_id,
            }
    else:
        platform_trace_service.emit(
            trace_id,
            "run_completed",
            run_id=trace_id,
            span_id=platform_trace_service.new_span_id("agentinvoke"),
            parent_span_id=span_id,
            status="success",
            agentId=agent_id,
            metadata={"mode": mode, "latencyMs": latency_ms},
        )
    return {
        "status": "success",
        "agent": agent,
        "request": {
            "input": {"message": prompt},
            "context": request_context,
            "runtimeOptions": runtime_options,
            "strategy": strategy,
            "llmConfig": _safe_llm_config_for_response(payload.llm_config),
            "availableTools": effective_available_tools,
            "runtimeEngine": runtime_engine,
        },
        "result": {
            "mode": mode,
            "answer": answer,
        },
        "stepOutputs": result.step_outputs if runtime_engine == "deepagent" and result is not None else {},
        "events": result.events if runtime_engine == "deepagent" and result is not None else [],
        "error": None,
        "latencyMs": latency_ms,
        "traceId": trace_id,
    }


@router.get("/v1/tools")
async def list_registered_tools() -> dict[str, Any]:
    builtin_items = tool_registry.describe_tools()
    custom_items = tool_definition_registry_service.list_tools()
    return {"items": builtin_items + custom_items}


@router.post("/v1/tools/draft")
async def create_tool_draft(payload: DraftPromptIn) -> dict[str, Any]:
    result = tool_definition_registry_service.create_draft(payload.prompt)
    if "draft" not in result:
        raise HTTPException(status_code=400, detail=result.get("message") or "failed to create tool draft")
    return {"status": "success", "draft": result["draft"]}


@router.post("/v1/tools")
@router.post("/v1/tools/register")
async def register_tool_definition(payload: dict[str, Any]) -> dict[str, Any]:
    policy_error = _validate_tool_manifest_policy(payload)
    if policy_error:
        raise HTTPException(status_code=400, detail=policy_error)
    result = tool_definition_registry_service.register_tool(payload)
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result["message"])
    trace_id = platform_trace_service.new_trace_id("toolreg")
    platform_trace_service.emit(
        trace_id,
        "tool_registered",
        run_id=trace_id,
        status="success",
        toolId=str(result["tool"].get("id") or payload.get("id") or ""),
        metadata={"version": result["tool"].get("version"), "status": result["tool"].get("status")},
    )
    return {"status": "success", "tool": result["tool"], "traceId": trace_id}


@router.get("/v1/tools/{tool_id}")
async def get_tool_definition(tool_id: str) -> dict[str, Any]:
    builtin = tool_registry.describe_tool(tool_id)
    if builtin is not None:
        return {"tool": builtin}
    tool = tool_definition_registry_service.get_tool(tool_id)
    if tool is None:
        raise HTTPException(status_code=404, detail=f"tool `{tool_id}` not found")
    return {"tool": tool}


@router.post("/v1/tools/{tool_id}/publish")
async def publish_tool_definition(tool_id: str) -> dict[str, Any]:
    result = tool_definition_registry_service.publish_tool(tool_id)
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result["message"])
    trace_id = platform_trace_service.new_trace_id("toolpub")
    platform_trace_service.emit(
        trace_id,
        "draft_published",
        run_id=trace_id,
        status="success",
        toolId=str(result["tool"].get("id") or tool_id),
        metadata={"entityType": "tool", "version": result["tool"].get("version")},
    )
    platform_trace_service.emit(
        trace_id,
        "definition_published",
        run_id=trace_id,
        status="success",
        toolId=str(result["tool"].get("id") or tool_id),
        metadata={"entityType": "tool", "version": result["tool"].get("version")},
    )
    return {"status": "success", "tool": result["tool"], "traceId": trace_id}


@router.get("/v1/personal-skills/tree")
async def list_personal_skill_tree() -> dict[str, Any]:
    tree = personal_skill_tree_service.list_tree()
    return {"status": "success", **tree}


@router.post("/v1/personal-skills/path")
async def set_personal_skill_path(payload: PersonalSkillPathIn) -> dict[str, Any]:
    result = personal_skill_tree_service.set_root_path(payload.path)
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result["message"])
    tree = personal_skill_tree_service.list_tree()
    return {"status": "success", **tree}


@router.post("/v1/unified/execute/stream")
async def execute_unified_stream(payload: UnifiedRequest, request: Request):
    if payload.request_type != "chat":
        raise HTTPException(status_code=400, detail="stream execute only supports requestType=chat")
    confirmed = bool((payload.inputs or {}).get("confirmed"))
    if not confirmed:
        raise HTTPException(status_code=400, detail="Please confirm plan before execute")
    query = (payload.messages or [{"content": ""}])[0].get("content", "")
    confirmed_plan = (payload.inputs or {}).get("confirmedPlan")
    execution_plan = (payload.inputs or {}).get("executionPlan")
    plan_supplement = (payload.inputs or {}).get("planSupplement")
    task_checklist = (payload.inputs or {}).get("taskChecklist")
    missing_skills = (payload.inputs or {}).get("missingSkills")
    confirmed_skills = (payload.inputs or {}).get("confirmedSkills")
    auto_install_missing = bool((payload.inputs or {}).get("autoInstallMissing"))
    step_approvals = (payload.inputs or {}).get("stepApprovals")
    step_overrides = (payload.inputs or {}).get("stepOverrides")
    step_executions = (payload.inputs or {}).get("stepExecutions")
    clawhub_selected = (payload.inputs or {}).get("clawhubSelectedSlugs")
    if isinstance(clawhub_selected, list):
        for slug in [str(x).strip() for x in clawhub_selected if str(x).strip()]:
            capability_service.register_clawhub_skill(slug)
    plan_lines: list[str] = []
    if isinstance(confirmed_plan, list):
        plan_lines = [str(item).strip() for item in confirmed_plan if str(item).strip()]
        if plan_lines:
            query += "\n\n[Confirmed Plan]\n" + "\n".join(
                f"{idx + 1}. {line}" for idx, line in enumerate(plan_lines)
            )
    elif isinstance(execution_plan, dict):
        raw_steps = execution_plan.get("steps")
        if isinstance(raw_steps, list):
            for item in raw_steps:
                if not isinstance(item, dict):
                    continue
                action = str(item.get("action", "")).strip()
                if action:
                    plan_lines.append(action)
        if plan_lines:
            query += "\n\n[Confirmed Plan]\n" + "\n".join(
                f"{idx + 1}. {line}" for idx, line in enumerate(plan_lines)
            )
    if isinstance(plan_supplement, str) and plan_supplement.strip():
        query += f"\n\n[Supplement]\n{plan_supplement.strip()}"
    if isinstance(task_checklist, list):
        checklist_lines = []
        for item in task_checklist:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text", "")).strip()
            done = bool(item.get("done"))
            if not text:
                continue
            checklist_lines.append(f"- [{'x' if done else ' '}] {text}")
        if checklist_lines:
            query += "\n\n[Task Checklist]\n" + "\n".join(checklist_lines)
    if isinstance(clawhub_selected, list):
        slugs = [str(x).strip() for x in clawhub_selected if str(x).strip()]
        if slugs:
            query += "\n\n[User-approved ClawHub skills]\n" + "\n".join(f"- {s}" for s in slugs)
    strategy = _get_strategy(payload)

    default_mode = strategy
    if isinstance(execution_plan, dict):
        m = execution_plan.get("mode")
        if isinstance(m, str) and m.strip():
            default_mode = m.strip()

    steps = normalize_execution_steps(
        execution_plan=execution_plan if isinstance(execution_plan, dict) else None,
        confirmed_plan=confirmed_plan if isinstance(confirmed_plan, list) else None,
        step_executions=step_executions if isinstance(step_executions, list) else None,
        default_mode=default_mode,
        step_overrides=step_overrides if isinstance(step_overrides, dict) else None,
    )
    steps = _augment_steps_for_query(query, steps)

    otie_request = _build_otie_request(payload, query)
    intent = otie_intent_service.normalize(otie_request)

    deepagent_record: dict[str, Any] | None = None
    if len(steps) == 1:
        step_agent_id = str(steps[0].get("agent") or "").strip()
        if step_agent_id and step_agent_id not in {"agent", "react", "workflow", "auto"}:
            deepagent_record = _get_registered_deepagent_record(step_agent_id)

    plan = (
        _build_otie_plan_from_steps(
            request_id=payload.request_id,
            intent_id=intent.intent_id,
            default_mode=default_mode,
            steps=steps,
        )
        if steps
        else await otie_planner.build_plan(intent)
    )

    async def event_stream():
        if deepagent_record is not None:
            allowed_tool_ids = [
                str(item).strip()
                for item in (deepagent_record.get("availableTools") or [])
                if str(item).strip()
            ]
            deep_trace_id = platform_trace_service.new_trace_id("deepstream")
            deep_run_id = platform_trace_service.new_trace_id("deepstream-run")
            deepagent_result = await deepagent_runtime_adapter.invoke(
                deepagent_record,
                request=DeepAgentInvokeRequest(
                    input={"message": query},
                    context=(payload.inputs or {}).get("context")
                    if isinstance((payload.inputs or {}).get("context"), dict)
                    else {},
                    runtime_options={},
                    llm_config=_get_llm_config(payload),
                ),
                context=DeepAgentInvokeContext(
                    trace_id=deep_trace_id,
                    run_id=deep_run_id,
                    user_id=_current_user_id(request),
                    agent_id=str(deepagent_record.get("id") or ""),
                    tenant_id=payload.tenant_id,
                    allowed_tool_ids=allowed_tool_ids,
                ),
            )
            step_name = str(steps[0].get("action") or query).strip() if steps else query
            step_id = str(steps[0].get("id") or "s1").strip() if steps else "s1"
            yield _sse_event({"type": "trace", "traceId": deep_trace_id})
            yield _sse_event({"type": "run_started", "runId": deep_run_id, "traceId": deep_trace_id})
            yield _sse_event(
                {
                    "type": "step_started",
                    "runId": deep_run_id,
                    "stepId": step_id,
                    "stepName": step_name,
                    "kind": "agent",
                }
            )
            for event in deepagent_result.events:
                shaped = dict(event)
                shaped.setdefault("runId", deep_run_id)
                shaped.setdefault("stepId", step_id)
                shaped.setdefault("stepName", step_name)
                yield _sse_event(shaped)
            yield _sse_event(
                {
                    "type": "step_completed",
                    "runId": deep_run_id,
                    "stepId": step_id,
                    "stepName": step_name,
                    "status": "success" if deepagent_result.status == "success" else deepagent_result.status,
                    "output": deepagent_result.answer,
                }
            )
            yield _sse_event(
                {
                    "type": "run_completed",
                    "runId": deep_run_id,
                    "status": deepagent_result.status,
                    "finalAnswer": deepagent_result.answer,
                }
            )
            yield _sse_event({'type': 'done', 'mode': deepagent_result.mode, 'answer': deepagent_result.answer, 'blocked': deepagent_result.status != 'success'})
            yield _sse_event({'type': 'trace_summary', 'trace': {'total': len(deepagent_result.events), 'success': 1 if deepagent_result.status == 'success' else 0, 'failed': 0 if deepagent_result.status == 'success' else 1}, 'runId': deep_run_id})
            return

        if isinstance(confirmed_skills, list):
            for skill_id in [str(x).strip() for x in confirmed_skills if str(x).strip()]:
                yield _sse_event({'type': 'skill_start', 'skill': skill_id})
                result = skill_executor_service.execute(skill_id, query)
                yield _sse_event({'type': 'skill_result', **result})
        if isinstance(missing_skills, list):
            install_events = capability_service.install_events_for_missing(
                [str(x) for x in missing_skills if str(x).strip()],
                auto_install=auto_install_missing,
            )
            for evt in install_events:
                yield _sse_event(evt)
        result = await otie_runtime.run(
            intent,
            plan,
            step_approvals=step_approvals if isinstance(step_approvals, dict) else {},
        )
        yield _sse_event({'type': 'trace', 'traceId': result.trace_id})
        yield _sse_event({'type': 'run_started', 'runId': result.run_id, 'traceId': result.trace_id})
        success_count = 0
        failed_count = 0
        step_names = _plan_step_names(plan)
        for event in result.events:
            event_type = str(event.get("type") or "")
            if event_type == "step_completed":
                success_count += 1
            if event_type == "run_finished" and str(event.get("status")) in {"failed", "awaiting_approval"}:
                failed_count += 1
            shaped = _frontend_event_from_trace(
                event,
                run_id=result.run_id,
                step_names=step_names,
                step_outputs=result.step_outputs,
            )
            if shaped is not None:
                yield _sse_event(shaped)
            yield _sse_event(event)
        if result.status == "awaiting_approval":
            pending_step = ""
            for event in result.events:
                if event.get("type") == "state_transition" and event.get("toState") == "awaiting_approval":
                    pending_step = str(event.get("stepId") or "")
                    break
            yield _sse_event({'type': 'approval_required', 'stepId': pending_step, 'decision': 'pending'})
        yield _sse_event({'type': 'run_completed', 'runId': result.run_id, 'status': result.status, 'finalAnswer': result.final_answer})
        yield _sse_event({'type': 'done', 'mode': plan.mode, 'answer': result.final_answer, 'blocked': result.status == 'awaiting_approval'})
        yield _sse_event({'type': 'trace_summary', 'trace': {'total': len(plan.steps), 'success': success_count, 'failed': failed_count}, 'runId': result.run_id})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/v1/traces/{trace_id}")
async def get_trace(trace_id: str) -> dict[str, Any]:
    events = trace_store.read_trace(trace_id)
    if not events:
        raise HTTPException(status_code=404, detail="trace not found")
    approvals = approval_store.list_for_trace(trace_id)
    return {"traceId": trace_id, "events": events, "approvals": approvals}


@router.get("/v1/traces/{trace_id}/events")
async def get_trace_events(trace_id: str) -> dict[str, Any]:
    events = trace_store.read_trace(trace_id)
    if not events:
        raise HTTPException(status_code=404, detail="trace not found")
    return {"traceId": trace_id, "events": events}


@router.get("/v1/runs/{run_id}")
async def get_run_trace(run_id: str) -> dict[str, Any]:
    run = otie_trace_service.get_run(run_id)
    if run is None:
        events = trace_store.read_trace(run_id)
        if not events:
            raise HTTPException(status_code=404, detail="run not found")
        latest = events[-1]
        return {
            "runId": run_id,
            "status": latest.get("status") or "unknown",
            "traceId": run_id,
            "events": events,
        }
    return run


@router.get("/v1/traces")
async def find_traces(request_id: Optional[str] = Query(None, alias="requestId")) -> dict[str, Any]:
    if not request_id:
        raise HTTPException(status_code=400, detail="requestId query param is required")
    return {"traceIds": trace_store.find_by_request_id(request_id)}


@router.get("/v1/metrics/kpi")
async def get_metrics_kpi() -> dict[str, Any]:
    return {"status": "success", "kpi": metrics_service.kpi_snapshot()}


@router.post("/v1/plan-records/save")
async def save_plan_record(payload: PlanRecordSaveIn) -> dict[str, Any]:
    path = plan_record_service.save_plan_record(
        query=payload.query,
        intent_description=payload.intent_description,
        mode=payload.mode,
        plan_lines=payload.plan_lines,
        recommended_skills=payload.recommended_skills,
        supplement=payload.supplement,
    )
    return {"status": "success", "path": path}
