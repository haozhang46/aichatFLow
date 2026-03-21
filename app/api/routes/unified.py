from uuid import uuid4
from datetime import datetime
import json
import time
from typing import Any, Optional

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import (
    agent_registry_service,
    approval_store,
    capability_service,
    executor_service,
    metrics_service,
    personal_skill_tree_service,
    plan_record_service,
    routing_service,
    skill_executor_service,
    trace_store,
    otie_runtime,
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
)
from app.core.config import settings
from app.services.clawhub_service import search_skills as clawhub_search_skills
from app.services.clawhub_plan_analysis import build_clawhub_plan_suggestions

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
    label: str
    description: str = ""


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
    return OtieRequestInput(
        requestId=payload.request_id,
        tenantId=payload.tenant_id,
        requestType=payload.request_type,
        messages=[{"role": "user", "content": query}],
        inputs=payload.inputs or {},
        metadata=payload.metadata or {},
    )


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
                    toolArgs={"query": str(step.get("action") or "")},
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


async def _resolve_otie_plan_for_payload(
    payload: UnifiedRequest,
    *,
    query: str,
    strategy: str,
) -> tuple[OtieRequestInput, Any, ExecutionPlan]:
    otie_request = _build_otie_request(payload, query)
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
async def execute_unified(payload: UnifiedRequest):
    # For chat requests, use LangChain/LangGraph orchestrator to select agent/react/workflow automatically.
    if payload.request_type == "chat":
        query = (payload.messages or [{"content": ""}])[0].get("content", "")
        strategy = _get_strategy(payload)
        started = time.monotonic()
        _, intent, plan = await _resolve_otie_plan_for_payload(payload, query=query, strategy=strategy)
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
    return {"items": agent_registry_service.list_agents()}


@router.post("/v1/agents")
async def create_agent_registry(payload: AgentCreateIn) -> dict[str, Any]:
    result = agent_registry_service.create_agent(payload.agent_id, payload.label, payload.description)
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return {"status": "success", "agent": result["agent"]}


@router.delete("/v1/agents/{agent_id}")
async def delete_agent_registry(agent_id: str) -> dict[str, Any]:
    result = agent_registry_service.delete_agent(agent_id)
    if not result["ok"]:
        raise HTTPException(status_code=404, detail=result["message"])
    return {"status": "success"}


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
async def execute_unified_stream(payload: UnifiedRequest):
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

    otie_request = _build_otie_request(payload, query)
    intent = otie_intent_service.normalize(otie_request)
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
        if isinstance(confirmed_skills, list):
            for skill_id in [str(x).strip() for x in confirmed_skills if str(x).strip()]:
                yield f"data: {json.dumps({'type': 'skill_start', 'skill': skill_id}, ensure_ascii=False)}\n\n"
                result = skill_executor_service.execute(skill_id, query)
                yield f"data: {json.dumps({'type': 'skill_result', **result}, ensure_ascii=False)}\n\n"
        if isinstance(missing_skills, list):
            install_events = capability_service.install_events_for_missing(
                [str(x) for x in missing_skills if str(x).strip()],
                auto_install=auto_install_missing,
            )
            for evt in install_events:
                yield f"data: {json.dumps(evt, ensure_ascii=False)}\n\n"
        result = await otie_runtime.run(
            intent,
            plan,
            step_approvals=step_approvals if isinstance(step_approvals, dict) else {},
        )
        yield f"data: {json.dumps({'type': 'trace', 'traceId': result.trace_id}, ensure_ascii=False)}\n\n"
        success_count = 0
        failed_count = 0
        for event in result.events:
            event_type = str(event.get("type") or "")
            if event_type == "step_completed":
                success_count += 1
            if event_type == "run_finished" and str(event.get("status")) in {"failed", "awaiting_approval"}:
                failed_count += 1
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        if result.status == "awaiting_approval":
            pending_step = ""
            for event in result.events:
                if event.get("type") == "state_transition" and event.get("toState") == "awaiting_approval":
                    pending_step = str(event.get("stepId") or "")
                    break
            yield f"data: {json.dumps({'type': 'approval_required', 'stepId': pending_step, 'decision': 'pending'}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'done', 'mode': plan.mode, 'answer': result.final_answer, 'blocked': result.status == 'awaiting_approval'}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'trace_summary', 'trace': {'total': len(plan.steps), 'success': success_count, 'failed': failed_count}, 'runId': result.run_id}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/v1/traces/{trace_id}")
async def get_trace(trace_id: str) -> dict[str, Any]:
    events = trace_store.read_trace(trace_id)
    if not events:
        raise HTTPException(status_code=404, detail="trace not found")
    approvals = approval_store.list_for_trace(trace_id)
    return {"traceId": trace_id, "events": events, "approvals": approvals}


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
