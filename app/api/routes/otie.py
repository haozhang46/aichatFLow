from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

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


@router.post("/v1/otie/intent")
async def create_intent(payload: OtieRequestInput) -> dict[str, Any]:
    intent = otie_intent_service.normalize(payload)
    return {"status": "success", "intent": intent.model_dump(by_alias=True)}


@router.post("/v1/otie/plan")
async def create_plan(payload: OtiePlanRequest) -> dict[str, Any]:
    intent = payload.intent
    if intent is None:
        if payload.request is None:
            raise HTTPException(status_code=400, detail="request or intent is required")
        intent = otie_intent_service.normalize(payload.request)
    plan = await otie_planner.build_plan(intent)
    return {
        "status": "success",
        "intent": intent.model_dump(by_alias=True),
        "executionPlan": plan.model_dump(by_alias=True),
    }


@router.post("/v1/otie/run")
async def run_otie(payload: OtieRunRequest) -> dict[str, Any]:
    intent = payload.intent
    if intent is None:
        if payload.request is None:
            raise HTTPException(status_code=400, detail="request or intent is required")
        intent = otie_intent_service.normalize(payload.request)
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
