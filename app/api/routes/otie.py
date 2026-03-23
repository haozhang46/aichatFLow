from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.deps import (
    otie_intent_service,
    otie_planner,
    otie_runtime,
    otie_trace_service,
    tool_policy_service,
    tool_registry,
)
from app.contracts.otie import OtiePlanRequest, OtieRequestInput, OtieRunRequest

router = APIRouter()


class ToolInvokeRequest(BaseModel):
    args: dict[str, Any] = Field(default_factory=dict)


def _current_user_id(request: Request) -> str:
    for key in ("user_id", "userId", "uid", "session_user", "sessionUser"):
        value = request.cookies.get(key)
        if value and value.strip():
            return value.strip()
    return ""


def _with_current_user_metadata(metadata: dict[str, Any], request: Request) -> dict[str, Any]:
    current_user_id = _current_user_id(request)
    if not current_user_id:
        return metadata
    return {**metadata, "currentUserId": current_user_id}


def _build_tool_invoke_response(
    *,
    status: str,
    tool: dict[str, Any],
    args: dict[str, Any],
    result: Any,
    error: dict[str, Any] | None,
    latency_ms: int,
    trace_id: str,
) -> dict[str, Any]:
    return {
        "status": status,
        "tool": tool,
        "request": {"args": args},
        "args": args,
        "result": result,
        "error": error,
        "latencyMs": latency_ms,
        "traceId": trace_id,
    }


@router.post("/v1/otie/intent")
async def create_intent(payload: OtieRequestInput, request: Request) -> dict[str, Any]:
    intent = otie_intent_service.normalize(
        payload.model_copy(update={"metadata": _with_current_user_metadata(payload.metadata, request)})
    )
    return {"status": "success", "intent": intent.model_dump(by_alias=True)}


@router.post("/v1/otie/plan")
async def create_plan(payload: OtiePlanRequest, request: Request) -> dict[str, Any]:
    intent = payload.intent
    if intent is None:
        if payload.request is None:
            raise HTTPException(status_code=400, detail="request or intent is required")
        intent = otie_intent_service.normalize(
            payload.request.model_copy(
                update={"metadata": _with_current_user_metadata(payload.request.metadata, request)}
            )
        )
    else:
        intent = intent.model_copy(update={"metadata": _with_current_user_metadata(intent.metadata, request)})
    plan = await otie_planner.build_plan(intent)
    return {
        "status": "success",
        "intent": intent.model_dump(by_alias=True),
        "executionPlan": plan.model_dump(by_alias=True),
    }


@router.post("/v1/otie/run")
async def run_otie(payload: OtieRunRequest, request: Request) -> dict[str, Any]:
    intent = payload.intent
    if intent is None:
        if payload.request is None:
            raise HTTPException(status_code=400, detail="request or intent is required")
        intent = otie_intent_service.normalize(
            payload.request.model_copy(
                update={"metadata": _with_current_user_metadata(payload.request.metadata, request)}
            )
        )
    else:
        intent = intent.model_copy(update={"metadata": _with_current_user_metadata(intent.metadata, request)})
    plan = payload.plan or await otie_planner.build_plan(intent)
    result = await otie_runtime.run(intent, plan, step_approvals=payload.step_approvals)
    return {"status": "success", "run": result.model_dump(by_alias=True)}


@router.get("/v1/otie/runs/{run_id}")
async def get_otie_run(run_id: str) -> dict[str, Any]:
    run = otie_trace_service.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return {"status": "success", "run": run}


@router.get("/v1/otie/tools")
async def list_otie_tools() -> dict[str, Any]:
    return {
        "status": "success",
        "items": [{**item, **tool_policy_service.status_for(str(item["id"]))} for item in tool_registry.describe_tools()],
        "policy": tool_policy_service.snapshot(),
    }


@router.post("/v1/otie/tools/{tool_id}/invoke")
async def invoke_otie_tool(tool_id: str, payload: ToolInvokeRequest, request: Request) -> dict[str, Any]:
    if not tool_registry.has_tool(tool_id):
        raise HTTPException(status_code=404, detail="tool not found")
    tool_meta = tool_registry.describe_tool(tool_id) or {"id": tool_id}
    policy_check = tool_policy_service.validate_invoke(tool_id)
    if not bool(policy_check.get("ok")):
        return _build_tool_invoke_response(
            status="failed",
            tool={**tool_meta, **tool_policy_service.status_for(tool_id)},
            args=payload.args,
            result=None,
            error={"code": policy_check.get("code") or "tool_not_allowed", "message": policy_check.get("message")},
            latency_ms=0,
            trace_id="",
        )
    started = time.monotonic()
    context = {"currentUserId": _current_user_id(request), "traceSource": "otie_tool_invoke"}
    try:
        result = await tool_registry.execute(tool_id, payload.args, context=context)
    except Exception as exc:
        trace_id = str(context.get("traceId") or "")
        error_code = "tool_not_allowed" if isinstance(exc, PermissionError) else "tool_invoke_failed"
        return _build_tool_invoke_response(
            status="failed",
            tool={**tool_meta, **tool_policy_service.status_for(tool_id)},
            args=payload.args,
            result=None,
            error={"code": error_code, "message": str(exc)},
            latency_ms=int((time.monotonic() - started) * 1000),
            trace_id=trace_id,
        )
    trace_id = str(context.get("traceId") or "")
    return _build_tool_invoke_response(
        status="success",
        tool={**tool_meta, **tool_policy_service.status_for(tool_id)},
        args=payload.args,
        result=result,
        error=None,
        latency_ms=int((time.monotonic() - started) * 1000),
        trace_id=trace_id,
    )
