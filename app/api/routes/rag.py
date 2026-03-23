from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from app.api.deps import rag_service

router = APIRouter()


class RagDocumentIn(BaseModel):
    tenant_id: str = Field(alias="tenantId")
    scope: str
    title: str
    content: str
    source: str = ""
    tags: list[str] = Field(default_factory=list)
    document_id: Optional[str] = Field(default=None, alias="documentId")


class RagSearchIn(BaseModel):
    tenant_id: str = Field(alias="tenantId")
    query: str
    scope: Optional[str] = None
    top_k: int = Field(default=5, alias="topK")
    min_score: float = Field(default=0.3, alias="minScore")


class RagScopeIn(BaseModel):
    tenant_id: str = Field(alias="tenantId")
    scope: str


class RagBatchItemIn(BaseModel):
    scope: Optional[str] = None
    title: str = ""
    content: str = ""
    url: str = ""
    file_path: str = Field(default="", alias="filePath")
    source: str = ""
    tags: list[str] = Field(default_factory=list)
    document_id: Optional[str] = Field(default=None, alias="documentId")


class RagBatchIn(BaseModel):
    tenant_id: str = Field(alias="tenantId")
    scope: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    items: list[RagBatchItemIn]


@router.post("/v1/rag/documents")
async def upsert_rag_document(payload: RagDocumentIn) -> dict[str, Any]:
    try:
        doc = await rag_service.upsert_document(
            tenant_id=payload.tenant_id,
            scope=payload.scope,
            title=payload.title,
            content=payload.content,
            source=payload.source,
            tags=payload.tags,
            document_id=payload.document_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"status": "success", "document": doc}


@router.delete("/v1/rag/documents/{document_id}")
async def delete_rag_document(
    document_id: str,
    tenant_id: str = Query(..., alias="tenantId"),
) -> dict[str, Any]:
    try:
        result = await rag_service.delete_document(tenant_id=tenant_id, document_id=document_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"status": "success", **result}


@router.post("/v1/rag/documents/batch")
async def batch_ingest_rag_documents(payload: RagBatchIn) -> dict[str, Any]:
    try:
        result = await rag_service.batch_ingest(
            tenant_id=payload.tenant_id,
            items=[
                item.model_dump(by_alias=True, exclude_none=True)
                for item in payload.items
            ],
            default_scope=payload.scope,
            default_tags=payload.tags,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"status": "success", "result": result}


@router.post("/v1/rag/documents/upload")
async def upload_rag_documents(
    tenant_id: str = Form(..., alias="tenantId"),
    scope: str = Form(...),
    tags_raw: str = Form("", alias="tags"),
    files: list[UploadFile] = File(...),
) -> dict[str, Any]:
    try:
        parsed_tags = [item.strip() for item in tags_raw.split(",") if item.strip()]
        result = await rag_service.ingest_uploaded_files(
            tenant_id=tenant_id,
            scope=scope,
            tags=parsed_tags,
            files=[
                {
                    "filename": upload.filename or "upload.bin",
                    "content": await upload.read(),
                }
                for upload in files
            ],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"status": "success", "result": result}


@router.get("/v1/rag/scopes")
async def list_rag_scopes(tenant_id: str = Query(..., alias="tenantId")) -> dict[str, Any]:
    return {"status": "success", "tenantId": tenant_id, "items": rag_service.list_scopes(tenant_id)}


@router.post("/v1/rag/scopes")
async def create_rag_scope(payload: RagScopeIn) -> dict[str, Any]:
    try:
        result = rag_service.create_scope(payload.tenant_id, payload.scope)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "success", **result}


@router.get("/v1/rag/documents")
async def list_rag_documents(
    tenant_id: str = Query(..., alias="tenantId"),
    scope: Optional[str] = Query(None),
) -> dict[str, Any]:
    return {"status": "success", "tenantId": tenant_id, "items": rag_service.list_documents(tenant_id, scope)}


@router.post("/v1/rag/search")
async def search_rag(payload: RagSearchIn) -> dict[str, Any]:
    try:
        result = await rag_service.search(
            tenant_id=payload.tenant_id,
            query=payload.query,
            scope=payload.scope,
            top_k=payload.top_k,
            min_score=payload.min_score,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"status": "success", "result": result}


@router.get("/v1/rag/graph")
async def get_rag_graph(
    tenant_id: str = Query(..., alias="tenantId"),
    scope: Optional[str] = Query(None),
) -> dict[str, Any]:
    return {"status": "success", "tenantId": tenant_id, "graph": rag_service.build_graph(tenant_id, scope)}
