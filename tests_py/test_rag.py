from unittest.mock import AsyncMock, patch
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.services.rag_service import RagService


def test_otie_plan_adds_retrieval_step_when_rag_enabled():
    client = TestClient(app)
    resp = client.post(
        "/v1/otie/plan",
        json={
            "request": {
                "requestId": "rag-plan-1",
                "tenantId": "tenant-a",
                "requestType": "chat",
                "messages": [{"role": "user", "content": "退款规则是什么？"}],
                "inputs": {"rag": {"enabled": True, "scope": "refund-policy", "topK": 4}},
            }
        },
    )
    assert resp.status_code == 200
    steps = resp.json()["executionPlan"]["steps"]
    retrieval_steps = [step for step in steps if step["kind"] == "tool" and step["toolId"] == "retrieval"]
    assert retrieval_steps
    assert retrieval_steps[0]["toolArgs"]["scope"] == "refund-policy"
    assert retrieval_steps[0]["toolArgs"]["topK"] == 4


def test_rag_routes_return_expected_payloads():
    client = TestClient(app)

    with patch("app.api.routes.rag.rag_service.upsert_document", new=AsyncMock(return_value={"documentId": "doc_1"})):
        upsert = client.post(
            "/v1/rag/documents",
            json={
                "tenantId": "tenant-a",
                "scope": "refund-policy",
                "title": "退款规则",
                "content": "支付后 7 天内可退款。",
            },
        )
    assert upsert.status_code == 200
    assert upsert.json()["document"]["documentId"] == "doc_1"

    with patch("app.api.routes.rag.rag_service.delete_document", new=AsyncMock(return_value={"documentId": "doc_1", "deleted": True})):
        delete = client.delete("/v1/rag/documents/doc_1?tenantId=tenant-a")
    assert delete.status_code == 200
    assert delete.json()["deleted"] is True

    with patch(
        "app.api.routes.rag.rag_service.batch_ingest",
        new=AsyncMock(return_value={"total": 2, "success": 2, "failed": 0, "items": []}),
    ):
        batch = client.post(
            "/v1/rag/documents/batch",
            json={
                "tenantId": "tenant-a",
                "scope": "refund-policy",
                "items": [
                    {"url": "https://example.com/a"},
                    {"filePath": "/tmp/test.txt"},
                ],
            },
        )
    assert batch.status_code == 200
    assert batch.json()["result"]["success"] == 2

    with patch("app.api.routes.rag.rag_service.list_scopes", return_value=["refund-policy", "vip-policy"]):
        scopes = client.get("/v1/rag/scopes?tenantId=tenant-a")
    assert scopes.status_code == 200
    assert scopes.json()["items"] == ["refund-policy", "vip-policy"]

    with patch(
        "app.api.routes.rag.rag_service.list_documents",
        return_value=[{"documentId": "doc_1", "scope": "refund-policy", "title": "退款规则"}],
    ):
        docs = client.get("/v1/rag/documents?tenantId=tenant-a&scope=refund-policy")
    assert docs.status_code == 200
    assert docs.json()["items"][0]["documentId"] == "doc_1"

    with patch(
        "app.api.routes.rag.rag_service.search",
        new=AsyncMock(
            return_value={
                "tenantId": "tenant-a",
                "query": "退款规则",
                "scope": "refund-policy",
                "topK": 5,
                "minScore": 0.3,
                "hits": [{"documentId": "doc_1", "chunkId": "doc_1_chunk_1", "score": 0.88}],
            }
        ),
    ):
        search = client.post(
            "/v1/rag/search",
            json={"tenantId": "tenant-a", "query": "退款规则", "scope": "refund-policy"},
        )
    assert search.status_code == 200
    assert search.json()["result"]["hits"][0]["documentId"] == "doc_1"

    with patch(
        "app.api.routes.rag.rag_service.build_graph",
        return_value={"nodes": [{"id": "scope:refund-policy"}], "edges": []},
    ):
        graph = client.get("/v1/rag/graph?tenantId=tenant-a&scope=refund-policy")
    assert graph.status_code == 200
    assert graph.json()["graph"]["nodes"][0]["id"] == "scope:refund-policy"

    with patch(
        "app.api.routes.rag.rag_service.ingest_uploaded_files",
        new=AsyncMock(return_value={"total": 1, "success": 1, "failed": 0, "items": [{"ok": True, "title": "guide.pdf"}]}),
    ):
        upload = client.post(
            "/v1/rag/documents/upload",
            data={"tenantId": "tenant-a", "scope": "refund-policy", "tags": "policy,pdf"},
            files={"files": ("guide.pdf", b"%PDF-1.4", "application/pdf")},
        )
    assert upload.status_code == 200
    assert upload.json()["result"]["success"] == 1


def test_rag_service_reads_pdf_and_docx_files(tmp_path: Path):
    service = RagService()

    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")

    class FakePage:
        def extract_text(self):
            return "PDF policy content"

    class FakePdfReader:
        def __init__(self, path: str):
            assert path.endswith("sample.pdf")
            self.pages = [FakePage()]

    with patch("app.services.rag_service.PdfReader", FakePdfReader):
        assert service._read_file_content(str(pdf_path)) == "PDF policy content"

    docx_path = tmp_path / "sample.docx"
    with zipfile.ZipFile(docx_path, "w") as archive:
        archive.writestr(
            "word/document.xml",
            (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                "<w:body><w:p><w:r><w:t>Docx policy content</w:t></w:r></w:p></w:body></w:document>"
            ),
        )

    assert service._read_file_content(str(docx_path)) == "Docx policy content"


def test_rag_service_reads_epub_files(tmp_path: Path):
    service = RagService()
    epub_path = tmp_path / "sample.epub"
    with zipfile.ZipFile(epub_path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr(
            "META-INF/container.xml",
            (
                '<?xml version="1.0"?>'
                '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
                "</rootfiles></container>"
            ),
        )
        archive.writestr(
            "OEBPS/content.opf",
            (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
                '<manifest><item id="chap1" href="chapter1.xhtml" media-type="application/xhtml+xml"/></manifest>'
                '<spine><itemref idref="chap1"/></spine>'
                "</package>"
            ),
        )
        archive.writestr(
            "OEBPS/chapter1.xhtml",
            (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<html xmlns="http://www.w3.org/1999/xhtml"><body>'
                "<h1>Chapter One</h1><p>Epub policy content</p></body></html>"
            ),
        )

    text = service._read_file_content(str(epub_path))
    assert "Chapter One" in text
    assert "Epub policy content" in text
