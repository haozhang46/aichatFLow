from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx

from app.core.config import settings


class RagService:
    def __init__(self) -> None:
        root = Path(__file__).resolve().parents[2]
        self._rag_dir = root / "data" / "rag"
        self._rag_dir.mkdir(parents=True, exist_ok=True)
        self._catalog_path = self._rag_dir / "catalog.json"
        if not self._catalog_path.exists():
            self._catalog_path.write_text("[]", encoding="utf-8")

    async def upsert_document(
        self,
        *,
        tenant_id: str,
        scope: str,
        title: str,
        content: str,
        source: str = "",
        tags: list[str] | None = None,
        document_id: str | None = None,
    ) -> dict[str, Any]:
        scope_value = scope.strip()
        title_value = title.strip() or "Untitled"
        content_value = content.strip()
        if not tenant_id.strip():
            raise ValueError("tenant_id is required")
        if not scope_value:
            raise ValueError("scope is required")
        if not content_value:
            raise ValueError("content is required")

        doc_id = document_id or f"ragdoc_{uuid4().hex[:12]}"
        now = datetime.utcnow().isoformat()
        chunks = self._chunk_content(content_value)
        record = {
            "documentId": doc_id,
            "tenantId": tenant_id,
            "scope": scope_value,
            "title": title_value,
            "content": content_value,
            "source": source.strip(),
            "tags": [str(tag).strip() for tag in (tags or []) if str(tag).strip()],
            "updatedAt": now,
            "createdAt": now,
            "chunks": [
                {
                    "chunkId": f"{doc_id}_chunk_{idx + 1}",
                    "chunkIndex": idx,
                    "content": chunk,
                }
                for idx, chunk in enumerate(chunks)
            ],
        }

        docs = self._read_catalog()
        replaced = False
        for idx, existing in enumerate(docs):
            if str(existing.get("documentId")) == doc_id:
                record["createdAt"] = existing.get("createdAt", now)
                docs[idx] = record
                replaced = True
                break
        if not replaced:
            docs.append(record)
        self._write_catalog(docs)

        collection_name = self._collection_name(tenant_id)
        await self._ensure_collection(collection_name, tenant_id)
        payload = [
            {
                "content": chunk["content"],
                "document_id": record["documentId"],
                "metadata": {
                    "tenantId": tenant_id,
                    "scope": scope_value,
                    "title": title_value,
                    "source": record["source"],
                    "tags": record["tags"],
                    "chunkId": chunk["chunkId"],
                    "chunkIndex": chunk["chunkIndex"],
                    "updatedAt": now,
                },
            }
            for chunk in record["chunks"]
        ]
        await self._request("POST", f"/api/v2/collections/{collection_name}/documents", json=payload)
        return record

    async def search(
        self,
        *,
        tenant_id: str,
        query: str,
        scope: str | None = None,
        top_k: int = 5,
        min_score: float = 0.3,
    ) -> dict[str, Any]:
        query_value = query.strip()
        scope_value = scope.strip() if isinstance(scope, str) else ""
        if not tenant_id.strip():
            raise ValueError("tenant_id is required")
        if not query_value:
            raise ValueError("query is required")

        collection_name = self._collection_name(tenant_id)
        search_payload: dict[str, Any] = {"text": query_value}
        if scope_value:
            search_payload["metadata"] = {"scope": scope_value}
        raw_results = await self._request(
            "POST",
            f"/api/v2/collections/{collection_name}/search",
            params={"limit": max(1, top_k)},
            json=search_payload,
        )
        hits: list[dict[str, Any]] = []
        for item in self._coerce_results(raw_results):
            metadata = item.get("metadata") or {}
            score = float(item.get("score") or 0.0)
            if score < min_score:
                continue
            hits.append(
                {
                    "documentId": str(item.get("document_id") or metadata.get("documentId") or ""),
                    "chunkId": str(metadata.get("chunkId") or item.get("uuid") or ""),
                    "title": str(metadata.get("title") or item.get("title") or "Untitled"),
                    "scope": str(metadata.get("scope") or ""),
                    "source": str(metadata.get("source") or ""),
                    "tags": list(metadata.get("tags") or []),
                    "score": round(score, 4),
                    "content": str(item.get("content") or item.get("page_content") or ""),
                }
            )

        return {
            "tenantId": tenant_id,
            "query": query_value,
            "scope": scope_value or None,
            "topK": max(1, top_k),
            "minScore": float(min_score),
            "hits": hits[: max(1, top_k)],
        }

    def list_scopes(self, tenant_id: str) -> list[str]:
        scopes = {
            str(item.get("scope") or "").strip()
            for item in self._read_catalog()
            if str(item.get("tenantId") or "") == tenant_id and str(item.get("scope") or "").strip()
        }
        return sorted(scopes)

    def list_documents(self, tenant_id: str, scope: str | None = None) -> list[dict[str, Any]]:
        scope_value = scope.strip() if isinstance(scope, str) else ""
        docs = []
        for item in self._read_catalog():
            if str(item.get("tenantId") or "") != tenant_id:
                continue
            if scope_value and str(item.get("scope") or "") != scope_value:
                continue
            docs.append(item)
        docs.sort(key=lambda item: str(item.get("updatedAt") or ""), reverse=True)
        return docs

    def build_graph(self, tenant_id: str, scope: str | None = None) -> dict[str, Any]:
        docs = self.list_documents(tenant_id, scope=scope)
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        seen_scopes: set[str] = set()
        for doc in docs:
            scope_value = str(doc.get("scope") or "")
            if scope_value and scope_value not in seen_scopes:
                seen_scopes.add(scope_value)
                nodes.append(
                    {
                        "id": f"scope:{scope_value}",
                        "type": "scope",
                        "label": scope_value,
                        "meta": {"scope": scope_value},
                    }
                )
            doc_id = str(doc.get("documentId") or "")
            nodes.append(
                {
                    "id": f"document:{doc_id}",
                    "type": "document",
                    "label": str(doc.get("title") or doc_id),
                    "meta": doc,
                }
            )
            if scope_value:
                edges.append(
                    {
                        "id": f"edge:scope:{scope_value}->{doc_id}",
                        "source": f"scope:{scope_value}",
                        "target": f"document:{doc_id}",
                    }
                )
            for chunk in doc.get("chunks") or []:
                chunk_id = str(chunk.get("chunkId") or "")
                nodes.append(
                    {
                        "id": f"chunk:{chunk_id}",
                        "type": "chunk",
                        "label": chunk_id,
                        "meta": {
                            "documentId": doc_id,
                            "scope": scope_value,
                            **chunk,
                        },
                    }
                )
                edges.append(
                    {
                        "id": f"edge:{doc_id}->{chunk_id}",
                        "source": f"document:{doc_id}",
                        "target": f"chunk:{chunk_id}",
                    }
                )
        return {"nodes": nodes, "edges": edges}

    async def _ensure_collection(self, collection_name: str, tenant_id: str) -> None:
        try:
            await self._request("GET", f"/api/v2/collections/{collection_name}")
            return
        except RuntimeError as exc:
            if "404" not in str(exc):
                raise
        await self._request(
            "POST",
            f"/api/v2/collections/{collection_name}",
            json={
                "description": f"Tenant knowledge base for {tenant_id}",
                "metadata": {"tenantId": tenant_id},
                "embedding_dimensions": settings.zep_embedding_dimensions,
            },
        )

    def _headers(self) -> dict[str, str]:
        if not settings.zep_api_key.strip():
            raise RuntimeError("ZEP_API_KEY is not configured")
        return {
            "Authorization": f"Api-Key {settings.zep_api_key}",
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
    ) -> Any:
        base_url = settings.zep_base_url.rstrip("/")
        url = f"{base_url}{path}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(
                method,
                url,
                headers=self._headers(),
                params=params,
                json=json,
            )
        if response.status_code >= 400:
            raise RuntimeError(f"Zep request failed ({response.status_code}) for {path}: {response.text[:300]}")
        if not response.text.strip():
            return {}
        return response.json()

    def _coerce_results(self, raw: Any) -> list[dict[str, Any]]:
        if isinstance(raw, dict):
            for key in ("results", "documents", "items", "matches"):
                value = raw.get(key)
                if isinstance(value, list):
                    return [self._coerce_result_item(item) for item in value]
            return []
        if isinstance(raw, list):
            return [self._coerce_result_item(item) for item in raw]
        value = getattr(raw, "results", None) or getattr(raw, "documents", None) or getattr(raw, "matches", None)
        if isinstance(value, list):
            return [self._coerce_result_item(item) for item in value]
        return []

    def _coerce_result_item(self, item: Any) -> dict[str, Any]:
        if isinstance(item, dict):
            return item
        return {
            "content": getattr(item, "content", "") or getattr(item, "page_content", ""),
            "score": getattr(item, "score", 0.0),
            "metadata": getattr(item, "metadata", {}) or {},
            "document_id": getattr(item, "document_id", "") or getattr(item, "documentId", ""),
            "uuid": getattr(item, "uuid", "") or getattr(item, "id", ""),
            "title": getattr(item, "title", ""),
        }

    def _read_catalog(self) -> list[dict[str, Any]]:
        try:
            raw = json.loads(self._catalog_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(raw, list):
            return []
        return [item for item in raw if isinstance(item, dict)]

    def _write_catalog(self, docs: list[dict[str, Any]]) -> None:
        self._catalog_path.write_text(json.dumps(docs, ensure_ascii=False, indent=2), encoding="utf-8")

    def _chunk_content(self, content: str) -> list[str]:
        text = content.strip()
        if not text:
            return []
        size = max(200, settings.rag_chunk_size)
        overlap = max(0, min(settings.rag_chunk_overlap, size // 2))
        chunks: list[str] = []
        cursor = 0
        while cursor < len(text):
            chunks.append(text[cursor : cursor + size].strip())
            if cursor + size >= len(text):
                break
            cursor += size - overlap
        return [chunk for chunk in chunks if chunk]

    def _collection_name(self, tenant_id: str) -> str:
        prefix = settings.zep_collection_prefix.strip() or "aichatflow"
        suffix = tenant_id.strip().replace(" ", "-")
        return f"{prefix}-{suffix}"
