from __future__ import annotations

import csv
import json
import math
import posixpath
import re
import zipfile
from datetime import datetime
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any
from uuid import uuid4
from xml.etree import ElementTree

import httpx
import lancedb
from pypdf import PdfReader

from app.core.config import settings


class RagService:
    def __init__(self) -> None:
        root = Path(__file__).resolve().parents[2]
        self._rag_dir = root / "data" / "rag"
        self._rag_dir.mkdir(parents=True, exist_ok=True)
        vector_path = settings.rag_vector_db_path.strip()
        self._vector_dir = Path(vector_path).expanduser() if vector_path else self._rag_dir / "lancedb"
        self._vector_dir.mkdir(parents=True, exist_ok=True)
        self._vector_table_name = "rag_chunks"
        self._vector_db = None
        self._catalog_path = self._rag_dir / "catalog.json"
        self._scope_catalog_path = self._rag_dir / "scopes.json"
        if not self._catalog_path.exists():
            self._catalog_path.write_text("[]", encoding="utf-8")
        if not self._scope_catalog_path.exists():
            self._scope_catalog_path.write_text("[]", encoding="utf-8")

    def create_scope(self, tenant_id: str, scope: str) -> dict[str, Any]:
        scope_value = scope.strip()
        if not tenant_id.strip():
            raise ValueError("tenant_id is required")
        if not scope_value:
            raise ValueError("scope is required")
        self._register_scope(tenant_id, scope_value)
        return {"tenantId": tenant_id, "scope": scope_value}

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

        self._register_scope(tenant_id, scope_value)
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

        chunk_payload = [
            {
                "chunkId": str(chunk["chunkId"]),
                "documentId": record["documentId"],
                "tenantId": tenant_id,
                "scope": scope_value,
                "title": title_value,
                "source": record["source"],
                "tags": record["tags"],
                "content": chunk["content"],
                "chunkIndex": int(chunk["chunkIndex"]),
                "updatedAt": now,
            }
            for chunk in record["chunks"]
        ]
        await self._replace_document_vectors(record["documentId"], chunk_payload)
        return record

    def get_document(self, tenant_id: str, document_id: str) -> dict[str, Any] | None:
        for item in self._read_catalog():
            if str(item.get("tenantId") or "") != tenant_id:
                continue
            if str(item.get("documentId") or "") == document_id:
                return item
        return None

    async def delete_document(self, *, tenant_id: str, document_id: str) -> dict[str, Any]:
        existing = self.get_document(tenant_id, document_id)
        if existing is None:
            raise ValueError("document not found")
        docs = [
            item
            for item in self._read_catalog()
            if not (
                str(item.get("tenantId") or "") == tenant_id
                and str(item.get("documentId") or "") == document_id
            )
        ]
        self._write_catalog(docs)

        self._delete_document_vectors(tenant_id=tenant_id, document_id=document_id)
        return {"documentId": document_id, "deleted": True}

    async def batch_ingest(
        self,
        *,
        tenant_id: str,
        items: list[dict[str, Any]],
        default_scope: str | None = None,
        default_tags: list[str] | None = None,
    ) -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        for item in items:
            try:
                source = str(item.get("source") or "").strip()
                scope = str(item.get("scope") or default_scope or "").strip()
                title = str(item.get("title") or "").strip()
                tags = [str(tag).strip() for tag in (item.get("tags") or default_tags or []) if str(tag).strip()]
                content = await self._resolve_ingest_content(item)
                title_value = title or self._derive_title(item)
                document = await self.upsert_document(
                    tenant_id=tenant_id,
                    scope=scope,
                    title=title_value,
                    content=content,
                    source=source or str(item.get("url") or item.get("filePath") or ""),
                    tags=tags,
                    document_id=str(item.get("documentId") or "").strip() or None,
                )
                results.append({"ok": True, "documentId": document["documentId"], "title": document["title"]})
            except Exception as exc:
                results.append(
                    {
                        "ok": False,
                        "title": str(item.get("title") or item.get("url") or item.get("filePath") or "unknown"),
                        "error": str(exc),
                    }
                )
        return {
            "total": len(items),
            "success": len([item for item in results if item.get("ok")]),
            "failed": len([item for item in results if not item.get("ok")]),
            "items": results,
        }

    async def ingest_uploaded_files(
        self,
        *,
        tenant_id: str,
        scope: str,
        files: list[dict[str, Any]],
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        for item in files:
            filename = str(item.get("filename") or "").strip()
            raw = item.get("content")
            if not isinstance(raw, (bytes, bytearray)):
                results.append({"ok": False, "title": filename or "unknown", "error": "invalid file payload"})
                continue
            try:
                content = self._read_uploaded_content(filename=filename, raw_bytes=bytes(raw))
                document = await self.upsert_document(
                    tenant_id=tenant_id,
                    scope=scope,
                    title=filename or "Untitled",
                    content=content,
                    source=filename,
                    tags=tags,
                )
                results.append({"ok": True, "documentId": document["documentId"], "title": document["title"]})
            except Exception as exc:
                results.append({"ok": False, "title": filename or "unknown", "error": str(exc)})
        return {
            "total": len(files),
            "success": len([item for item in results if item.get("ok")]),
            "failed": len([item for item in results if not item.get("ok")]),
            "items": results,
        }

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

        table = self._open_vector_table()
        if table is None:
            return {
                "tenantId": tenant_id,
                "query": query_value,
                "scope": scope_value or None,
                "topK": max(1, top_k),
                "minScore": float(min_score),
                "hits": [],
            }
        query_vector = (await self._embed_texts([query_value]))[0]
        where_clauses = [f"tenantId = '{self._escape_sql_string(tenant_id)}'"]
        if scope_value:
            where_clauses.append(f"scope = '{self._escape_sql_string(scope_value)}'")
        raw_results = (
            table.search(query_vector)
            .where(" AND ".join(where_clauses))
            .limit(max(1, top_k))
            .to_list()
        )
        hits: list[dict[str, Any]] = []
        for item in raw_results:
            distance = float(item.get("_distance") or 0.0)
            score = max(0.0, round(1.0 - min(distance / 2.0, 1.0), 4))
            if score < min_score:
                continue
            hits.append(
                {
                    "documentId": str(item.get("documentId") or ""),
                    "chunkId": str(item.get("chunkId") or ""),
                    "title": str(item.get("title") or "Untitled"),
                    "scope": str(item.get("scope") or ""),
                    "source": str(item.get("source") or ""),
                    "tags": list(item.get("tags") or []),
                    "score": round(score, 4),
                    "content": str(item.get("content") or ""),
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
        doc_scopes = {
            str(item.get("scope") or "").strip()
            for item in self._read_catalog()
            if str(item.get("tenantId") or "") == tenant_id and str(item.get("scope") or "").strip()
        }
        registered_scopes = {
            str(item.get("scope") or "").strip()
            for item in self._read_scope_catalog()
            if str(item.get("tenantId") or "") == tenant_id and str(item.get("scope") or "").strip()
        }
        return sorted(doc_scopes | registered_scopes)

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

    async def _resolve_ingest_content(self, item: dict[str, Any]) -> str:
        if str(item.get("content") or "").strip():
            return str(item.get("content")).strip()
        file_path = str(item.get("filePath") or "").strip()
        if file_path:
            return self._read_file_content(file_path)
        url = str(item.get("url") or "").strip()
        if url:
            return await self._fetch_url_content(url)
        raise ValueError("content, filePath, or url is required")

    def _read_file_content(self, file_path: str) -> str:
        path = Path(file_path).expanduser()
        if not path.is_absolute():
            path = (Path.cwd() / path).resolve()
        if not path.exists() or not path.is_file():
            raise ValueError(f"file not found: {file_path}")
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            content = self._read_pdf_content(path)
        elif suffix == ".docx":
            content = self._read_docx_content(path)
        elif suffix == ".epub":
            content = self._read_epub_content(path)
        elif suffix in {".csv", ".tsv"}:
            content = self._read_delimited_text(path, delimiter="\t" if suffix == ".tsv" else ",")
        else:
            content = self._read_text_file(path)
        if not content.strip():
            raise ValueError(f"file is empty: {file_path}")
        return content.strip()

    def _read_uploaded_content(self, *, filename: str, raw_bytes: bytes) -> str:
        suffix = Path(filename).suffix.lower()
        if suffix == ".pdf":
            content = self._read_pdf_bytes(raw_bytes, filename=filename)
        elif suffix == ".docx":
            content = self._read_docx_bytes(raw_bytes, filename=filename)
        elif suffix == ".epub":
            content = self._read_epub_bytes(raw_bytes, filename=filename)
        elif suffix in {".csv", ".tsv"}:
            content = self._read_delimited_bytes(raw_bytes, filename=filename, delimiter="\t" if suffix == ".tsv" else ",")
        else:
            content = self._read_text_bytes(raw_bytes, filename=filename)
        if not content.strip():
            raise ValueError(f"file is empty: {filename}")
        return content.strip()

    def _read_text_file(self, path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                return path.read_text(encoding="utf-8", errors="ignore")
            except Exception as exc:
                raise ValueError(f"unsupported text encoding for file: {path}") from exc

    def _read_text_bytes(self, raw_bytes: bytes, *, filename: str) -> str:
        try:
            return raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            try:
                return raw_bytes.decode("utf-8", errors="ignore")
            except Exception as exc:
                raise ValueError(f"unsupported text encoding for file: {filename}") from exc

    def _read_pdf_content(self, path: Path) -> str:
        try:
            reader = PdfReader(str(path))
        except Exception as exc:
            raise ValueError(f"failed to parse pdf: {path}") from exc
        pages: list[str] = []
        for page in reader.pages:
            text = page.extract_text() or ""
            if text.strip():
                pages.append(text.strip())
        return "\n\n".join(pages)

    def _read_pdf_bytes(self, raw_bytes: bytes, *, filename: str) -> str:
        try:
            reader = PdfReader(BytesIO(raw_bytes))
        except Exception as exc:
            raise ValueError(f"failed to parse pdf: {filename}") from exc
        pages: list[str] = []
        for page in reader.pages:
            text = page.extract_text() or ""
            if text.strip():
                pages.append(text.strip())
        return "\n\n".join(pages)

    def _read_docx_content(self, path: Path) -> str:
        try:
            with zipfile.ZipFile(path) as archive:
                raw = archive.read("word/document.xml")
        except Exception as exc:
            raise ValueError(f"failed to parse docx: {path}") from exc

        try:
            root = ElementTree.fromstring(raw)
        except ElementTree.ParseError as exc:
            raise ValueError(f"failed to parse docx xml: {path}") from exc

        namespaces = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        paragraphs: list[str] = []
        for paragraph in root.findall(".//w:p", namespaces):
            texts = [node.text or "" for node in paragraph.findall(".//w:t", namespaces)]
            merged = "".join(texts).strip()
            if merged:
                paragraphs.append(merged)
        return "\n\n".join(paragraphs)

    def _read_docx_bytes(self, raw_bytes: bytes, *, filename: str) -> str:
        try:
            with zipfile.ZipFile(BytesIO(raw_bytes)) as archive:
                raw = archive.read("word/document.xml")
        except Exception as exc:
            raise ValueError(f"failed to parse docx: {filename}") from exc

        try:
            root = ElementTree.fromstring(raw)
        except ElementTree.ParseError as exc:
            raise ValueError(f"failed to parse docx xml: {filename}") from exc

        namespaces = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        paragraphs: list[str] = []
        for paragraph in root.findall(".//w:p", namespaces):
            texts = [node.text or "" for node in paragraph.findall(".//w:t", namespaces)]
            merged = "".join(texts).strip()
            if merged:
                paragraphs.append(merged)
        return "\n\n".join(paragraphs)

    def _read_epub_bytes(self, raw_bytes: bytes, *, filename: str) -> str:
        try:
            with zipfile.ZipFile(BytesIO(raw_bytes)) as archive:
                chapter_paths = self._epub_chapter_paths(archive)
                sections: list[str] = []
                for chapter_path in chapter_paths:
                    try:
                        chapter_raw = archive.read(chapter_path)
                    except KeyError:
                        continue
                    html = chapter_raw.decode("utf-8", errors="ignore")
                    text = self._extract_text_from_html(html)
                    if text.strip():
                        sections.append(text.strip())
        except Exception as exc:
            raise ValueError(f"failed to parse epub: {filename}") from exc
        return "\n\n".join(sections)

    def _read_epub_content(self, path: Path) -> str:
        try:
            with zipfile.ZipFile(path) as archive:
                chapter_paths = self._epub_chapter_paths(archive)
                sections: list[str] = []
                for chapter_path in chapter_paths:
                    try:
                        chapter_raw = archive.read(chapter_path)
                    except KeyError:
                        continue
                    html = chapter_raw.decode("utf-8", errors="ignore")
                    text = self._extract_text_from_html(html)
                    if text.strip():
                        sections.append(text.strip())
        except Exception as exc:
            raise ValueError(f"failed to parse epub: {path}") from exc
        return "\n\n".join(sections)

    def _epub_chapter_paths(self, archive: zipfile.ZipFile) -> list[str]:
        try:
            container_raw = archive.read("META-INF/container.xml")
            container_root = ElementTree.fromstring(container_raw)
            rootfile = container_root.find(".//{*}rootfile")
            if rootfile is None:
                raise ValueError("missing rootfile")
            opf_path = rootfile.attrib.get("full-path", "")
            if not opf_path:
                raise ValueError("missing package path")
            opf_raw = archive.read(opf_path)
            package_root = ElementTree.fromstring(opf_raw)
        except Exception:
            return self._fallback_epub_content_paths(archive)

        manifest: dict[str, str] = {}
        for item in package_root.findall(".//{*}manifest/{*}item"):
            item_id = item.attrib.get("id", "").strip()
            href = item.attrib.get("href", "").strip()
            media_type = item.attrib.get("media-type", "").strip().lower()
            if not item_id or not href:
                continue
            if "html" not in media_type and "xhtml" not in media_type and not href.lower().endswith((".html", ".xhtml", ".htm")):
                continue
            manifest[item_id] = posixpath.normpath(posixpath.join(posixpath.dirname(opf_path), href))

        ordered: list[str] = []
        for itemref in package_root.findall(".//{*}spine/{*}itemref"):
            ref = itemref.attrib.get("idref", "").strip()
            path = manifest.get(ref)
            if path:
                ordered.append(path)
        return ordered or self._fallback_epub_content_paths(archive)

    def _fallback_epub_content_paths(self, archive: zipfile.ZipFile) -> list[str]:
        candidates = [
            name
            for name in archive.namelist()
            if name.lower().endswith((".xhtml", ".html", ".htm")) and not name.startswith("META-INF/")
        ]
        return sorted(candidates)

    def _read_delimited_text(self, path: Path, *, delimiter: str) -> str:
        raw = self._read_text_file(path)
        reader = csv.reader(StringIO(raw), delimiter=delimiter)
        rows = [" | ".join(cell.strip() for cell in row if cell is not None) for row in reader]
        return "\n".join(row for row in rows if row.strip())

    def _read_delimited_bytes(self, raw_bytes: bytes, *, filename: str, delimiter: str) -> str:
        raw = self._read_text_bytes(raw_bytes, filename=filename)
        reader = csv.reader(StringIO(raw), delimiter=delimiter)
        rows = [" | ".join(cell.strip() for cell in row if cell is not None) for row in reader]
        return "\n".join(row for row in rows if row.strip())

    async def _fetch_url_content(self, url: str) -> str:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(url)
        if response.status_code >= 400:
            raise ValueError(f"url fetch failed ({response.status_code}): {url}")
        content_type = response.headers.get("content-type", "").lower()
        text = response.text
        if "html" in content_type or "<html" in text.lower():
            text = self._extract_text_from_html(text)
        text = text.strip()
        if not text:
            raise ValueError(f"url content is empty: {url}")
        return text

    def _extract_text_from_html(self, html: str) -> str:
        text = re.sub(r"(?is)<script.*?>.*?</script>", " ", html)
        text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
        text = re.sub(r"(?s)<[^>]+>", " ", text)
        text = text.replace("&nbsp;", " ").replace("&amp;", "&")
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _derive_title(self, item: dict[str, Any]) -> str:
        for key in ("title", "url", "filePath"):
            value = str(item.get(key) or "").strip()
            if value:
                return Path(value).name or value
        return "Untitled"

    def _get_vector_db(self):
        if self._vector_db is None:
            self._vector_db = lancedb.connect(str(self._vector_dir))
        return self._vector_db

    def _open_vector_table(self):
        try:
            return self._get_vector_db().open_table(self._vector_table_name)
        except Exception:
            return None

    async def _replace_document_vectors(self, document_id: str, rows: list[dict[str, Any]]) -> None:
        self._delete_document_vectors(document_id=document_id)
        if not rows:
            return
        embeddings = await self._embed_texts([str(row["content"]) for row in rows])
        payload = [
            {
                **row,
                "vector": embedding,
            }
            for row, embedding in zip(rows, embeddings)
        ]
        table = self._open_vector_table()
        if table is None:
            self._get_vector_db().create_table(self._vector_table_name, data=payload)
            return
        table.add(payload)

    def _delete_document_vectors(self, *, document_id: str, tenant_id: str | None = None) -> None:
        table = self._open_vector_table()
        if table is None:
            return
        clauses = [f"documentId = '{self._escape_sql_string(document_id)}'"]
        if tenant_id:
            clauses.append(f"tenantId = '{self._escape_sql_string(tenant_id)}'")
        table.delete(" AND ".join(clauses))

    async def _embed_texts(self, texts: list[str]) -> list[list[float]]:
        cleaned = [text.strip() for text in texts if text.strip()]
        if not cleaned:
            return []
        base_url = settings.ollama_base_url.rstrip("/")
        model = settings.ollama_embed_model.strip()
        if not model:
            raise RuntimeError("OLLAMA_EMBED_MODEL is not configured")

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{base_url}/api/embed",
                json={"model": model, "input": cleaned},
            )
            if response.status_code < 400:
                data = response.json()
                embeddings = data.get("embeddings")
                if isinstance(embeddings, list) and embeddings:
                    return [self._normalize_vector(item) for item in embeddings]

            fallback_embeddings: list[list[float]] = []
            for text in cleaned:
                fallback_response = await client.post(
                    f"{base_url}/api/embeddings",
                    json={"model": model, "prompt": text},
                )
                if fallback_response.status_code >= 400:
                    raise RuntimeError(
                        f"Ollama embedding request failed ({fallback_response.status_code}): {fallback_response.text[:300]}"
                    )
                item = fallback_response.json().get("embedding")
                if not isinstance(item, list) or not item:
                    raise RuntimeError("Ollama embedding response did not include `embedding`")
                fallback_embeddings.append(self._normalize_vector(item))
            return fallback_embeddings

    def _normalize_vector(self, values: list[Any]) -> list[float]:
        vector = [float(value) for value in values]
        magnitude = math.sqrt(sum(value * value for value in vector))
        if magnitude <= 0:
            return vector
        return [value / magnitude for value in vector]

    def _escape_sql_string(self, value: str) -> str:
        return value.replace("'", "''")

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

    def _read_scope_catalog(self) -> list[dict[str, Any]]:
        try:
            raw = json.loads(self._scope_catalog_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(raw, list):
            return []
        return [item for item in raw if isinstance(item, dict)]

    def _write_scope_catalog(self, scopes: list[dict[str, Any]]) -> None:
        self._scope_catalog_path.write_text(json.dumps(scopes, ensure_ascii=False, indent=2), encoding="utf-8")

    def _register_scope(self, tenant_id: str, scope: str) -> None:
        scope_value = scope.strip()
        if not tenant_id.strip() or not scope_value:
            return
        scopes = self._read_scope_catalog()
        if any(
            str(item.get("tenantId") or "") == tenant_id and str(item.get("scope") or "").strip() == scope_value
            for item in scopes
        ):
            return
        scopes.append(
            {
                "tenantId": tenant_id,
                "scope": scope_value,
                "createdAt": datetime.utcnow().isoformat(),
            }
        )
        self._write_scope_catalog(scopes)

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
