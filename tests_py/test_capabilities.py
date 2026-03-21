from fastapi.testclient import TestClient

from app.main import app


def test_capabilities_endpoint_returns_agents_and_skills():
    client = TestClient(app)
    resp = client.get("/v1/capabilities")
    assert resp.status_code == 200
    body = resp.json()
    assert "agents" in body
    assert "skills" in body
    assert any(a["id"] == "agent" for a in body["agents"])
    assert any(a["id"] == "workflow" for a in body["agents"])
    assert "whitelist" in body
    assert len(body["skills"]) >= 1
    assert "manifest" in body["skills"][0]
    assert "toolId" in body["skills"][0]["manifest"]


def test_plan_includes_recommendation_metadata():
    client = TestClient(app)
    resp = client.post(
        "/v1/unified/plan",
        json={
            "requestId": "req-plan-1",
            "tenantId": "tenant-a",
            "requestType": "chat",
            "messages": [{"role": "user", "content": "帮我配置 skill 和 agent"}],
            "inputs": {"strategy": "workflow"},
        },
    )
    assert resp.status_code == 200
    output = resp.json()["output"]
    assert "recommendedAgent" in output
    assert "recommendedSkills" in output
    assert "missingSkills" in output
    assert "installRequired" in output
    assert "executionPlan" in output
    assert isinstance(output["executionPlan"].get("steps"), list)


def test_stream_emits_install_events_for_missing_skills():
    client = TestClient(app)
    resp = client.post(
        "/v1/unified/execute/stream",
        json={
            "requestId": "req-stream-1",
            "tenantId": "tenant-a",
            "requestType": "chat",
            "messages": [{"role": "user", "content": "配置 skill"}],
            "inputs": {
                "strategy": "workflow",
                "confirmed": True,
                    "confirmedPlan": ["步骤一", "步骤二"],
                "missingSkills": ["skill-installer"],
                "autoInstallMissing": True,
            },
        },
    )
    assert resp.status_code == 200
    body = resp.text
    assert '"type": "install"' in body
    assert '"skill": "skill-installer"' in body
    assert '"type": "step_start"' in body
    assert '"type": "step_done"' in body


def test_save_plan_record_to_specs_plan_folder():
    client = TestClient(app)
    resp = client.post(
        "/v1/plan-records/save",
        json={
            "query": "今天天气",
            "intentDescription": "用户想查询今天的天气并拿到建议",
            "mode": "workflow",
            "planLines": ["识别城市", "查询天气", "返回建议"],
            "recommendedSkills": ["find-skills"],
            "supplement": "",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert "/specs/main/plans/" in body["path"]


def test_plan_reuses_existing_plan_record_for_identical_query():
    client = TestClient(app)
    save = client.post(
        "/v1/plan-records/save",
        json={
            "query": "复用计划测试",
            "intentDescription": "复用已有计划记录",
            "mode": "agent",
            "planLines": ["步骤A", "步骤B"],
            "recommendedSkills": ["find-skills"],
            "supplement": "",
        },
    )
    assert save.status_code == 200

    resp = client.post(
        "/v1/unified/plan",
        json={
            "requestId": "req-plan-reuse-1",
            "tenantId": "tenant-a",
            "requestType": "chat",
            "messages": [{"role": "user", "content": "复用计划测试"}],
            "inputs": {"strategy": "auto"},
        },
    )
    assert resp.status_code == 200
    output = resp.json()["output"]
    assert output["reusedFromPlanRecord"] is True
    assert output["plan"] == ["步骤A", "步骤B"]
    assert output["intentDescription"] == "复用已有计划记录"
    assert output["planRecordPath"]


def test_capability_install_and_whitelist_update():
    client = TestClient(app)
    wl = client.post("/v1/capabilities/whitelist", json={"skillId": "find-skills", "enabled": True})
    assert wl.status_code == 200
    ins = client.post("/v1/capabilities/install", json={"skillId": "find-skills"})
    assert ins.status_code == 200
    assert ins.json()["status"] == "success"


def test_capabilities_search_and_pagination_and_online_add():
    client = TestClient(app)
    resp = client.get("/v1/capabilities?q=react&page=1&pageSize=1")
    assert resp.status_code == 200
    body = resp.json()
    assert "agents" in body
    assert body["page"] == 1
    assert body["pageSize"] == 1

    online = client.get("/v1/capabilities/online-search?q=weather")
    assert online.status_code == 200
    items = online.json()["items"]
    assert len(items) >= 1

    add = client.post("/v1/capabilities/add-online", json={"skillId": items[0]["id"]})
    assert add.status_code == 200
    assert add.json()["status"] == "success"


def test_self_built_agent_registry_crud():
    client = TestClient(app)
    create = client.post(
        "/v1/agents",
        json={"agentId": "local-planner", "label": "Local Planner", "description": "custom planner"},
    )
    assert create.status_code == 200
    lst = client.get("/v1/agents")
    assert lst.status_code == 200
    assert any(a["id"] == "local-planner" for a in lst.json()["items"])
    delete = client.delete("/v1/agents/local-planner")
    assert delete.status_code == 200


def test_plan_accepts_deepseek_llm_config_shape():
    client = TestClient(app)
    resp = client.post(
        "/v1/unified/plan",
        json={
            "requestId": "req-plan-deepseek-shape",
            "tenantId": "tenant-a",
            "requestType": "chat",
            "messages": [{"role": "user", "content": "hello"}],
            "inputs": {
                "strategy": "agent",
                "llmConfig": {
                    "provider": "deepseek",
                    "apiKey": "sk-test-value",
                    "baseUrl": "https://api.deepseek.com/v1",
                    "model": "deepseek-chat",
                },
            },
        },
    )
    assert resp.status_code == 200


def test_metrics_kpi_endpoint():
    client = TestClient(app)
    resp = client.get("/v1/metrics/kpi")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("status") == "success"
    assert "planSuccessRate" in body["kpi"]


def test_stream_includes_trace_event():
    client = TestClient(app)
    resp = client.post(
        "/v1/unified/execute/stream",
        json={
            "requestId": "req-trace-evt",
            "tenantId": "tenant-a",
            "requestType": "chat",
            "messages": [{"role": "user", "content": "hello"}],
            "inputs": {
                "strategy": "workflow",
                "confirmed": True,
                "confirmedPlan": ["步骤一", "步骤二"],
            },
        },
    )
    assert resp.status_code == 200
    assert '"type": "trace"' in resp.text
