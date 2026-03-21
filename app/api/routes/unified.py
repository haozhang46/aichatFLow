from uuid import uuid4
from datetime import datetime
import json
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
    policy_engine,
    routing_service,
    skill_executor_service,
    trace_store,
)
from app.schemas.unified import UnifiedRequest
from app.services.execution_steps import normalize_execution_steps
from app.orchestrator.graph import (
    build_plan_context,
    run_orchestrator,
    run_orchestrator_stream,
    run_orchestrator_stream_for_step,
)
from app.core.config import settings
from app.services.clawhub_service import search_skills as clawhub_search_skills
from app.services.clawhub_plan_analysis import build_clawhub_plan_suggestions
from app.services.schema_validation import validate_llm_text_against_schema

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


@router.post("/v1/unified/execute")
async def execute_unified(payload: UnifiedRequest):
    trace_id = f"trace_{uuid4().hex[:12]}"
    # For chat requests, use LangChain/LangGraph orchestrator to select agent/react/workflow automatically.
    if payload.request_type == "chat":
        query = (payload.messages or [{"content": ""}])[0].get("content", "")
        strategy = _get_strategy(payload)
        llm_config = _get_llm_config(payload)
        mode, answer, latency_ms = await run_orchestrator(query, strategy=strategy, llm_config=llm_config)
        return {
            "requestId": payload.request_id,
            "provider": "langchain",
            "status": "success",
            "output": {"mode": mode, "answer": answer},
            "error": None,
            "latencyMs": latency_ms,
            "traceId": trace_id,
            "fallbackUsed": False,
            "timestamp": datetime.utcnow().isoformat(),
        }

    # For workflow requests, keep the previous FastGPT/Dify execution path.
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
    return {
        "agents": builtin_agents + custom_agents,
        "skills": skills_page["items"],
        "skillsTotal": skills_page["total"],
        "page": skills_page["page"],
        "pageSize": skills_page["pageSize"],
        "whitelist": capability_service.list_whitelist(),
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
    llm_config = _get_llm_config(payload)

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

    trace_id = f"trace_{uuid4().hex[:12]}"
    policy = policy_engine

    async def event_stream():
        yield f"data: {json.dumps({'type': 'trace', 'traceId': trace_id}, ensure_ascii=False)}\n\n"
        trace_store.append(
            trace_id,
            {
                "type": "execution_start",
                "requestId": payload.request_id,
                "tenantId": payload.tenant_id,
                "stepCount": len(steps),
            },
        )

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

        if not steps:
            trace_store.append(trace_id, {"type": "note", "message": "no_structured_steps_single_orchestrator"})
            async for evt in run_orchestrator_stream(query, strategy=strategy, llm_config=llm_config):
                if evt.get("type") == "done":
                    trace_store.append(trace_id, {"type": "execution_done", "mode": evt.get("mode"), "answerPreview": str(evt.get("answer", ""))[:500]})
                yield f"data: {json.dumps(evt, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'trace_summary', 'trace': {'total': 0, 'success': 0, 'failed': 0}}, ensure_ascii=False)}\n\n"
            return

        step_stats = {"total": len(steps), "success": 0, "failed": 0}
        prior_summary = ""
        combined: list[str] = []

        for idx, step in enumerate(steps):
            step_id = str(step["id"])
            action = str(step["action"])
            step_skills = step.get("skills") or []
            skill_ids_for_policy = [str(s) for s in step_skills if str(s).strip()]

            yield f"data: {json.dumps({'type': 'step_start', 'stepId': step_id, 'stepIndex': idx, 'step': action, 'agent': step.get('agent'), 'skills': step_skills}, ensure_ascii=False)}\n\n"

            assessment = policy.assess_step(action, tool_ids=skill_ids_for_policy)
            allow = policy.is_step_allowed(assessment, step_id, step_approvals if isinstance(step_approvals, dict) else None)
            yield f"data: {json.dumps({'type': 'policy_check', 'stepId': step_id, 'stepIndex': idx, 'riskLevel': assessment.get('riskLevel'), 'allow': allow, 'deniedTool': assessment.get('deniedTool')}, ensure_ascii=False)}\n\n"

            if not allow:
                step_stats["failed"] += 1
                trace_store.append(
                    trace_id,
                    {
                        "type": "blocked",
                        "stepId": step_id,
                        "deniedTool": assessment.get("deniedTool"),
                        "riskLevel": assessment.get("riskLevel"),
                    },
                )
                if assessment.get("deniedTool"):
                    msg = f"策略拒绝：工具 `{assessment.get('deniedTool')}` 不在允许列表。"
                    yield f"data: {json.dumps({'type': 'step_done', 'stepId': step_id, 'stepIndex': idx, 'step': action, 'status': 'failed'}, ensure_ascii=False)}\n\n"
                    yield f"data: {json.dumps({'type': 'done', 'mode': strategy, 'answer': msg, 'blocked': False}, ensure_ascii=False)}\n\n"
                    yield f"data: {json.dumps({'type': 'trace_summary', 'trace': step_stats}, ensure_ascii=False)}\n\n"
                    return
                yield f"data: {json.dumps({'type': 'approval_required', 'stepId': step_id, 'stepIndex': idx, 'reason': 'high-risk action detected', 'decision': 'pending'}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'type': 'done', 'mode': strategy, 'answer': '执行已暂停：检测到高风险步骤，等待用户审批后继续。', 'blocked': True, 'pendingApprovalStepId': step_id}, ensure_ascii=False)}\n\n"
                return

            if (
                assessment.get("riskLevel") == "high"
                and isinstance(step_approvals, dict)
                and step_approvals.get(step_id)
            ):
                approval_store.append(
                    trace_id=trace_id,
                    request_id=payload.request_id,
                    tenant_id=payload.tenant_id,
                    step_id=step_id,
                    approved=True,
                    meta={"reason": "risk_high"},
                )

            for sk in skill_ids_for_policy:
                yield f"data: {json.dumps({'type': 'skill_start', 'skill': sk, 'stepId': step_id}, ensure_ascii=False)}\n\n"
                result = skill_executor_service.execute(sk, query)
                out = {**result, "stepId": step_id}
                yield f"data: {json.dumps({'type': 'skill_result', **out}, ensure_ascii=False)}\n\n"

            step_strat = _coerce_step_strategy(str(step.get("agent") or default_mode), strategy)
            step_answer = ""
            async for evt in run_orchestrator_stream_for_step(
                query,
                action,
                idx,
                len(steps),
                prior_summary,
                strategy=step_strat,
                llm_config=llm_config,
            ):
                if evt.get("type") == "done":
                    step_answer = str(evt.get("answer", ""))
                else:
                    yield f"data: {json.dumps(evt, ensure_ascii=False)}\n\n"

            output_schema = step.get("outputSchema")
            schema_mode = str((payload.inputs or {}).get("schemaValidationMode") or "warn").lower()
            if output_schema and isinstance(output_schema, dict) and schema_mode != "off":
                vr = validate_llm_text_against_schema(step_answer, output_schema)
                metrics_service.record_schema(ok=vr.ok)
                yield f"data: {json.dumps({'type': 'schema_check', 'stepId': step_id, 'stepIndex': idx, 'ok': vr.ok, 'error': vr.error}, ensure_ascii=False)}\n\n"
                trace_store.append(
                    trace_id,
                    {"type": "schema_check", "stepId": step_id, "ok": vr.ok, "error": vr.error},
                )
                if not vr.ok and schema_mode == "block":
                    step_stats["failed"] += 1
                    msg = f"步骤 {step_id} 输出未通过 JSON Schema：{vr.error or 'validation failed'}"
                    yield f"data: {json.dumps({'type': 'step_done', 'stepId': step_id, 'stepIndex': idx, 'step': action, 'status': 'failed'}, ensure_ascii=False)}\n\n"
                    yield f"data: {json.dumps({'type': 'done', 'mode': strategy, 'answer': msg, 'blocked': False}, ensure_ascii=False)}\n\n"
                    yield f"data: {json.dumps({'type': 'trace_summary', 'trace': step_stats}, ensure_ascii=False)}\n\n"
                    return
                if not vr.ok and schema_mode == "warn":
                    step_answer = f"{step_answer}\n\n[schema warning] {vr.error}"

            trace_store.append(
                trace_id,
                {"type": "step_llm_done", "stepId": step_id, "answerPreview": step_answer[:500]},
            )
            combined.append(f"### {step_id}\n{step_answer}")
            prior_summary = (prior_summary + f"\n{step_id}: {step_answer}")[-4000:]

            step_stats["success"] += 1
            yield f"data: {json.dumps({'type': 'step_done', 'stepId': step_id, 'stepIndex': idx, 'step': action, 'status': 'success'}, ensure_ascii=False)}\n\n"
            trace_store.append(trace_id, {"type": "step_completed", "stepId": step_id, "status": "success"})

        final_answer = "\n\n".join(combined)
        yield f"data: {json.dumps({'type': 'done', 'mode': strategy, 'answer': final_answer, 'latencyMs': 0}, ensure_ascii=False)}\n\n"
        trace_store.append(trace_id, {"type": "execution_finished", "answerPreview": final_answer[:500]})
        yield f"data: {json.dumps({'type': 'trace_summary', 'trace': step_stats}, ensure_ascii=False)}\n\n"

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
