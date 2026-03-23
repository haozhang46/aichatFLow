from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from app.api.deps import file_acl_service

router = APIRouter()


class FileAclRuleIn(BaseModel):
    userId: str
    path: str
    permissions: list[str]


def _require_admin(request: Request) -> None:
    role = str(request.cookies.get("role") or "").strip().lower()
    is_admin = str(request.cookies.get("is_admin") or "").strip().lower()
    if role == "admin" or is_admin in {"1", "true", "yes"}:
        return
    raise HTTPException(status_code=403, detail="admin permission required")


@router.get("/v1/files/acl")
async def list_file_acl(
    request: Request,
    user_id: Optional[str] = Query(default=None, alias="userId"),
    path: Optional[str] = Query(default=None),
) -> Dict[str, Any]:
    _require_admin(request)
    return {"status": "success", "rules": file_acl_service.list_rules(user_id=user_id, path_prefix=path)}


@router.post("/v1/files/acl")
async def upsert_file_acl(request: Request, payload: FileAclRuleIn) -> dict[str, Any]:
    _require_admin(request)
    try:
        rule = file_acl_service.upsert_rule(user_id=payload.userId.strip(), path=payload.path, permissions=payload.permissions)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "success", "rule": rule}


@router.delete("/v1/files/acl")
async def delete_file_acl(request: Request, user_id: str = Query(..., alias="userId"), path: str = Query(...)) -> dict[str, Any]:
    _require_admin(request)
    deleted = file_acl_service.delete_rule(user_id=user_id.strip(), path=path)
    if not deleted:
        raise HTTPException(status_code=404, detail="acl rule not found")
    return {"status": "success", "deleted": True}
