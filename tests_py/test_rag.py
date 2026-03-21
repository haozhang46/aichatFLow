from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app


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
