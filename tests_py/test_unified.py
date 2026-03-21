from fastapi.testclient import TestClient

from app.main import app


def _base_env():
    return {
        "id": "route-a",
        "tenantId": "tenant-a",
        "requestType": "chat",
        "primaryProvider": "fastgpt",
        "fallbackProvider": "dify",
        "timeoutMs": 1000,
        "enabled": True,
    }


def test_health():
    client = TestClient(app)
    resp = client.get("/v1/health")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_route_upsert_and_list():
    client = TestClient(app)
    create = client.post("/v1/routes", json=_base_env())
    assert create.status_code == 201
    lst = client.get("/v1/routes")
    assert lst.status_code == 200
    assert len(lst.json()) >= 1


def test_unified_route_validation():
    client = TestClient(app)
    resp = client.post(
        "/v1/unified/execute",
        # chat mode requires `messages`
        json={"requestId": "r1", "tenantId": "tenant-a", "requestType": "chat"},
    )
    assert resp.status_code == 422


def test_chat_strategy_override():
    client = TestClient(app)

    resp = client.post(
        "/v1/unified/execute",
        json={
            "requestId": "req-002",
            "tenantId": "tenant-a",
            "requestType": "chat",
            "messages": [{"role": "user", "content": "Please do react reasoning."}],
            "inputs": {"strategy": "react"},
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["provider"] == "langchain"
    assert body["output"]["mode"] == "react"
