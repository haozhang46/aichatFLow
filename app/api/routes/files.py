from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from app.api.deps import file_acl_service, file_service, platform_trace_service

router = APIRouter()


class FileWriteIn(BaseModel):
    path: str
    content: str = ""


class FileMkdirIn(BaseModel):
    path: str


class FilePatchIn(BaseModel):
    path: str
    content: str = ""
    mode: str = "append"


def _current_user_id(request: Request) -> str:
    for key in ("user_id", "userId", "uid", "session_user", "sessionUser"):
        value = request.cookies.get(key)
        if value and value.strip():
            return value.strip()
    raise HTTPException(status_code=401, detail="login required")


def _normalize_acl_path(path: str) -> str:
    value = path.strip().replace("\\", "/").strip("/")
    if not value:
        return "stories/"
    return f"stories/{value}"


def _check_access(request: Request, path: str, action: str) -> str:
    user_id = _current_user_id(request)
    acl_path = _normalize_acl_path(path)
    if not file_acl_service.is_allowed(user_id, acl_path, action):
        trace_id = platform_trace_service.new_trace_id("file")
        platform_trace_service.emit(
            trace_id,
            "acl_denied",
            run_id=trace_id,
            status="failed",
            userId=user_id,
            resourcePath=acl_path,
            metadata={"action": action, "source": "file_api"},
        )
        raise HTTPException(
            status_code=403,
            detail={"message": f"{action} access denied for `{acl_path}`", "code": "acl_denied", "traceId": trace_id},
        )
    return user_id


@router.get("/v1/files")
async def get_file(request: Request, path: str = Query(default="")) -> dict[str, Any]:
    user_id = _check_access(request, path, "read")
    try:
        result = file_service.read(path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    trace_id = platform_trace_service.new_trace_id("file")
    platform_trace_service.emit(
        trace_id,
        "file_read",
        run_id=trace_id,
        status="success",
        userId=user_id,
        resourcePath=_normalize_acl_path(path),
        metadata={"source": "file_api"},
    )
    return {"status": "success", "traceId": trace_id, **result}


@router.get("/v1/files/tree")
async def get_file_tree(request: Request, path: str = Query(default="")) -> dict[str, Any]:
    user_id = _check_access(request, path, "read")
    try:
        result = file_service.list_tree(path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    trace_id = platform_trace_service.new_trace_id("file")
    platform_trace_service.emit(
        trace_id,
        "file_read",
        run_id=trace_id,
        status="success",
        userId=user_id,
        resourcePath=_normalize_acl_path(path),
        metadata={"source": "file_api", "action": "list_tree"},
    )
    return {"status": "success", "traceId": trace_id, **result}


@router.put("/v1/files")
async def put_file(request: Request, payload: FileWriteIn) -> dict[str, Any]:
    user_id = _check_access(request, payload.path, "write")
    try:
        result = file_service.write(payload.path, payload.content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    trace_id = platform_trace_service.new_trace_id("file")
    platform_trace_service.emit(
        trace_id,
        "file_write",
        run_id=trace_id,
        status="success",
        userId=user_id,
        resourcePath=_normalize_acl_path(payload.path),
        metadata={"source": "file_api"},
    )
    return {"status": "success", "traceId": trace_id, **result}


@router.post("/v1/files/mkdir")
async def mkdir_file(request: Request, payload: FileMkdirIn) -> dict[str, Any]:
    user_id = _check_access(request, payload.path, "write")
    try:
        result = file_service.mkdir(payload.path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    trace_id = platform_trace_service.new_trace_id("file")
    platform_trace_service.emit(
        trace_id,
        "file_mkdir",
        run_id=trace_id,
        status="success",
        userId=user_id,
        resourcePath=_normalize_acl_path(payload.path),
        metadata={"source": "file_api"},
    )
    return {"status": "success", "traceId": trace_id, **result}


@router.patch("/v1/files")
async def patch_file(request: Request, payload: FilePatchIn) -> dict[str, Any]:
    user_id = _check_access(request, payload.path, "write")
    try:
        result = file_service.patch(payload.path, payload.content, mode=payload.mode)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    trace_id = platform_trace_service.new_trace_id("file")
    platform_trace_service.emit(
        trace_id,
        "file_patch",
        run_id=trace_id,
        status="success",
        userId=user_id,
        resourcePath=_normalize_acl_path(payload.path),
        metadata={"source": "file_api", "mode": payload.mode},
    )
    return {"status": "success", "traceId": trace_id, **result}


@router.delete("/v1/files")
async def delete_file(request: Request, path: str = Query(...)) -> dict[str, Any]:
    user_id = _check_access(request, path, "delete")
    try:
        result = file_service.delete(path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    trace_id = platform_trace_service.new_trace_id("file")
    platform_trace_service.emit(
        trace_id,
        "file_delete",
        run_id=trace_id,
        status="success",
        userId=user_id,
        resourcePath=_normalize_acl_path(path),
        metadata={"source": "file_api"},
    )
    return {"status": "success", "traceId": trace_id, **result}
