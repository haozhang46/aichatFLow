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
    assert body["output"]["runId"]
    assert body["traceId"] == body["output"]["runId"]


def test_unified_stream_executes_via_otie_runtime():
    client = TestClient(app)
    resp = client.post(
        "/v1/unified/execute/stream",
        json={
            "requestId": "req-stream-1",
            "tenantId": "tenant-a",
            "requestType": "chat",
            "messages": [{"role": "user", "content": "Find skills for workflow automation."}],
            "inputs": {
                "confirmed": True,
                "executionPlan": {
                    "planId": "plan-stream-1",
                    "mode": "agent",
                    "steps": [
                        {
                            "id": "s1",
                            "type": "llm",
                            "action": "Summarize the workflow automation request.",
                            "skills": ["find-skills"],
                            "dependsOn": [],
                            "agent": "agent",
                        }
                    ],
                },
            },
        },
    )
    assert resp.status_code == 200
    text = resp.text
    assert '"type": "trace"' in text
    assert '"type": "tool_call"' in text
    assert '"type": "done"' in text


def test_capabilities_includes_tools():
    client = TestClient(app)
    resp = client.get("/v1/capabilities")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body.get("tools"), list)
    tool_ids = {item["id"] for item in body["tools"]}
    assert "weather" in tool_ids
    assert "find-skills" in tool_ids


def test_tool_policy_endpoint_updates_capabilities():
    client = TestClient(app)
    resp = client.post(
        "/v1/capabilities/tools/policy",
        json={"toolId": "weather", "allowlisted": True, "denylisted": False},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["allowlisted"] is True
    cap = client.get("/v1/capabilities").json()
    weather = [item for item in cap["tools"] if item["id"] == "weather"][0]
    assert weather["allowlisted"] is True
    reset = client.post(
        "/v1/capabilities/tools/policy",
        json={"toolId": "weather", "allowlisted": False, "denylisted": False},
    )
    assert reset.status_code == 200
