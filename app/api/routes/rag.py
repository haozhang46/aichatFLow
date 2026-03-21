from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
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


@router.get("/v1/rag/scopes")
async def list_rag_scopes(tenant_id: str = Query(..., alias="tenantId")) -> dict[str, Any]:
    return {"status": "success", "tenantId": tenant_id, "items": rag_service.list_scopes(tenant_id)}


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
