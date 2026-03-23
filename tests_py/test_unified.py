import json
from fastapi.testclient import TestClient
from pathlib import Path
from unittest.mock import patch

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


def test_builtin_tool_descriptors_follow_manifest_shape():
    client = TestClient(app)
    resp = client.get("/v1/tools")
    assert resp.status_code == 200
    items = resp.json()["items"]
    weather = next(item for item in items if item["id"] == "weather")
    assert weather["kind"] == "builtin"
    assert weather["version"] == "0.1.0"
    assert weather["status"] == "published"
    assert weather["source"]["type"] == "core"
    assert weather["lifecycle"]["state"] == "published"


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


def test_otie_tool_invoke_returns_structured_error_for_denylisted_tool():
    client = TestClient(app)
    set_policy = client.post(
        "/v1/capabilities/tools/policy",
        json={"toolId": "weather", "allowlisted": False, "denylisted": True},
    )
    assert set_policy.status_code == 200

    try:
        resp = client.post("/v1/otie/tools/weather/invoke", json={"args": {"location": "Shanghai"}})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "failed"
        assert body["error"]["code"] == "tool_not_allowed"
        assert body["request"]["args"]["location"] == "Shanghai"
    finally:
        reset = client.post(
            "/v1/capabilities/tools/policy",
            json={"toolId": "weather", "allowlisted": False, "denylisted": False},
        )
        assert reset.status_code == 200


def test_capabilities_tools_include_required_user_inputs():
    client = TestClient(app)
    resp = client.get("/v1/capabilities")
    assert resp.status_code == 200
    tools = resp.json()["tools"]
    weather = [item for item in tools if item["id"] == "weather"][0]
    assert isinstance(weather.get("requiredUserInputs"), list)
    assert weather["requiredUserInputs"][0]["key"] == "location"


def test_agent_invoke_endpoint_runs_builtin_agent():
    client = TestClient(app)
    resp = client.post(
        "/v1/agents/agent/invoke",
        json={"prompt": "Write a short story opening."},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["agent"]["id"] == "agent"
    assert body["request"]["strategy"] == "agent"
    assert body["result"]["mode"] == "agent"
    assert "answer" in body["result"]


def test_agent_invoke_endpoint_runs_custom_agent_profile():
    client = TestClient(app)
    created = client.post(
        "/v1/agents",
        json={"agentId": "story-crafter", "label": "Story Crafter", "description": "Specialized in fiction writing."},
    )
    assert created.status_code == 200

    captured: dict[str, str] = {}

    async def fake_run_orchestrator(query: str, strategy: str = "auto", llm_config=None):
        captured["query"] = query
        captured["strategy"] = strategy
        return "agent", "custom answer", 12

    with patch("app.api.routes.unified.run_orchestrator", side_effect=fake_run_orchestrator):
        resp = client.post(
            "/v1/agents/story-crafter/invoke",
            json={"prompt": "Draft a fantasy opening scene."},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["result"]["answer"] == "custom answer"
    assert captured["strategy"] == "agent"
    assert "Story Crafter" in captured["query"]
    assert "Specialized in fiction writing." in captured["query"]

    deleted = client.delete("/v1/agents/story-crafter")
    assert deleted.status_code == 200


def test_agent_register_validates_available_tools():
    client = TestClient(app)
    resp = client.post(
        "/v1/agents/register",
        json={
            "agentId": "invalid-tools-agent",
            "label": "Invalid Tools Agent",
            "description": "Should fail.",
            "systemPrompt": "Use a missing tool.",
            "availableTools": ["missing-tool"],
        },
    )
    assert resp.status_code == 400
    assert "unknown tool" in str(resp.json()["detail"])


def test_tool_draft_endpoint_creates_validated_draft_record():
    client = TestClient(app)
    draft_path = None
    try:
        resp = client.post("/v1/tools/draft", json={"prompt": "Create a tool that summarizes markdown documents."})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "success"
        assert body["draft"]["status"] == "draft"
        assert body["draft"]["lifecycle"]["validation"]["status"] == "passed"
        assert body["draft"]["lifecycle"]["review"]["status"] == "pending"
        draft_id = body["draft"]["draftId"]
        draft_path = Path(f"data/drafts/tools/{draft_id}.json")
    finally:
        if draft_path is not None and draft_path.exists():
            draft_path.unlink()


def test_agent_draft_endpoint_creates_validated_draft_record():
    client = TestClient(app)
    draft_path = None
    try:
        resp = client.post("/v1/agents/draft", json={"prompt": "Create an agent that plans stories and manages outlines."})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "success"
        assert body["draft"]["status"] == "draft"
        assert body["draft"]["lifecycle"]["validation"]["status"] == "passed"
        assert body["draft"]["lifecycle"]["review"]["status"] == "pending"
        draft_id = body["draft"]["draftId"]
        draft_path = Path(f"data/drafts/agents/{draft_id}.json")
    finally:
        if draft_path is not None and draft_path.exists():
            draft_path.unlink()


def test_tool_register_validates_policy_allow_agents():
    client = TestClient(app)
    resp = client.post(
        "/v1/tools/register",
        json={
            "id": "policy-gated-tool",
            "name": "Policy Gated Tool",
            "description": "Only for known agents.",
            "version": "0.1.0",
            "kind": "http",
            "inputSchema": {"type": "object"},
            "endpoint": {"url": "https://example.com/tool", "timeoutMs": 5000},
            "policy": {"allowAgents": ["unknown-agent"]},
        },
    )
    assert resp.status_code == 400
    assert "unknown agent ids" in str(resp.json()["detail"])


def test_story_agent_is_available_and_uses_deepagent_runtime_configuration():
    client = TestClient(app)
    listed = client.get("/v1/agents")
    assert listed.status_code == 200
    items = listed.json()["items"]
    story_agent = next(item for item in items if item["id"] == "story-agent")
    assert story_agent["label"] == "Story Agent"

    captured: dict[str, object] = {}

    class FakeResult:
        status = "success"
        mode = "agent"
        answer = "story answer"
        events = []
        step_outputs = {}
        latency_ms = 10
        error = None

    async def fake_invoke(agent_spec, request, context):
        captured["agent_id"] = agent_spec["id"]
        captured["message"] = request.input["message"]
        captured["allowed_tool_ids"] = context.allowed_tool_ids
        return FakeResult()

    with patch("app.api.routes.unified.deepagent_runtime_adapter.invoke", side_effect=fake_invoke):
        resp = client.post(
            "/v1/agents/story-agent/invoke",
            json={"prompt": "Write a short sci-fi opening scene."},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["result"]["answer"] == "story answer"
    assert body["request"]["runtimeEngine"] == "deepagent"
    assert captured["agent_id"] == "story-agent"
    assert captured["message"] == "Write a short sci-fi opening scene."
    assert "retrieval" in (captured["allowed_tool_ids"] or [])


def test_otie_tool_invoke_supports_published_custom_http_tool():
    client = TestClient(app)
    tool_id = "custom-http-echo"
    tool_path = Path("data/registry/tools/custom-http-echo.json")

    manifest = {
        "id": tool_id,
        "name": "Custom HTTP Echo",
        "description": "Proxy to external HTTP tool.",
        "version": "0.1.0",
        "kind": "http",
        "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}},
        "endpoint": {"url": "https://example.com/tool", "timeoutMs": 5000},
    }

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"echo": "ok", "source": "custom-http"}

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json=None):
            assert url == "https://example.com/tool"
            assert json["args"]["query"] == "hello"
            assert "context" in json
            return FakeResponse()

    try:
        registered = client.post("/v1/tools/register", json=manifest)
        assert registered.status_code == 200
        published = client.post(f"/v1/tools/{tool_id}/publish")
        assert published.status_code == 200

        with patch("app.services.tool_executor_adapter_service.httpx.AsyncClient", return_value=FakeAsyncClient()):
            resp = client.post(
                f"/v1/otie/tools/{tool_id}/invoke",
                json={"args": {"query": "hello"}},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "success"
        assert body["tool"]["id"] == tool_id
        assert body["result"]["echo"] == "ok"
        assert body["result"]["source"] == "custom-http"
    finally:
        if tool_path.exists():
            tool_path.unlink()


def test_agent_invoke_prefers_published_agent_runtime_mode_and_system_prompt():
    client = TestClient(app)
    agent_id = "runtime-react-agent"
    agent_path = Path("data/registry/agents/runtime-react-agent.json")

    captured: dict[str, str] = {}

    async def fake_run_orchestrator(query: str, strategy: str = "auto", llm_config=None):
        captured["query"] = query
        captured["strategy"] = strategy
        return "react", "agent answer", 9

    try:
        created = client.post(
            "/v1/agents/register",
            json={
                "agentId": agent_id,
                "label": "Runtime React Agent",
                "description": "Custom runtime-configured agent.",
                "systemPrompt": "Always think in ReAct steps.",
            },
        )
        assert created.status_code == 200

        record = client.get(f"/v1/agents/{agent_id}").json()["agent"]
        record["runtime"] = {"mode": "react", "maxSteps": 6}
        record["availableTools"] = ["file-read", "retrieval"]
        update = client.post("/v1/agents/register", json={
            "agentId": agent_id,
            "label": record["name"],
            "description": record["description"],
            "systemPrompt": record["systemPrompt"],
        })
        assert update.status_code == 200
        # Persist the richer runtime fields directly for this contract test.
        agent_path.write_text(json.dumps({**record, "status": "registered"}, ensure_ascii=False, indent=2), encoding="utf-8")

        published = client.post(f"/v1/agents/{agent_id}/publish")
        assert published.status_code == 200

        with patch("app.api.routes.unified.run_orchestrator", side_effect=fake_run_orchestrator):
            resp = client.post(
                f"/v1/agents/{agent_id}/invoke",
                json={"prompt": "Continue the story."},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["result"]["answer"] == "agent answer"
        assert captured["strategy"] == "react"
        assert "Always think in ReAct steps." in captured["query"]
        assert "Available tools: file-read, retrieval" in captured["query"]
    finally:
        if agent_path.exists():
            agent_path.unlink()


def test_agent_invoke_supports_normalized_request_contract():
    client = TestClient(app)

    captured: dict[str, str] = {}

    async def fake_run_orchestrator(query: str, strategy: str = "auto", llm_config=None):
        captured["query"] = query
        captured["strategy"] = strategy
        return "agent", "normalized answer", 7

    with patch("app.api.routes.unified.run_orchestrator", side_effect=fake_run_orchestrator):
        resp = client.post(
            "/v1/agents/agent/invoke",
            json={
                "input": {"message": "Write a short ending."},
                "context": {"workspace": "stories/story-001"},
                "runtimeOptions": {"temperature": 0.2},
            },
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["request"]["input"]["message"] == "Write a short ending."
    assert body["request"]["context"]["workspace"] == "stories/story-001"
    assert body["request"]["runtimeOptions"]["temperature"] == 0.2
    assert body["result"]["answer"] == "normalized answer"


def test_agent_invoke_uses_deepagent_adapter_when_runtime_engine_is_deepagent():
    client = TestClient(app)
    agent_id = "deepagent-writer"
    agent_path = Path("data/registry/agents/deepagent-writer.json")

    captured: dict[str, object] = {}

    class FakeResult:
        status = "success"
        mode = "agent"
        answer = "deepagent answer"
        events = []
        step_outputs = {}
        latency_ms = 11
        error = None

    async def fake_invoke(agent_spec, request, context):
        captured["agent_id"] = agent_spec["id"]
        captured["message"] = request.input["message"]
        captured["allowed_tool_ids"] = context.allowed_tool_ids
        captured["trace_id"] = context.trace_id
        return FakeResult()

    try:
        created = client.post(
            "/v1/agents/register",
            json={
                "agentId": agent_id,
                "label": "DeepAgent Writer",
                "description": "DeepAgent-enabled custom writer.",
                "systemPrompt": "Write with persistence.",
                "availableTools": ["file-read"],
                "runtime": {"mode": "agent", "engine": "deepagent", "maxSteps": 6},
            },
        )
        assert created.status_code == 200

        published = client.post(f"/v1/agents/{agent_id}/publish")
        assert published.status_code == 200

        with patch("app.api.routes.unified.deepagent_runtime_adapter.invoke", side_effect=fake_invoke):
            resp = client.post(
                f"/v1/agents/{agent_id}/invoke",
                json={"input": {"message": "Continue the story."}},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "success"
        assert body["request"]["runtimeEngine"] == "deepagent"
        assert body["result"]["answer"] == "deepagent answer"
        assert captured["agent_id"] == agent_id
        assert captured["message"] == "Continue the story."
        assert captured["allowed_tool_ids"] == ["file-read"]
        assert isinstance(captured["trace_id"], str) and captured["trace_id"]
    finally:
        if agent_path.exists():
            agent_path.unlink()


def test_story_agent_deepagent_hydrates_file_memory_and_prefetches_retrieval():
    client = TestClient(app)
    captured: dict[str, object] = {}
    writebacks: list[tuple[str, dict[str, object]]] = []

    async def fake_file_read(path, *, user_id, agent_id, allowed_tool_ids, trace_id):
        if path == "story-demo/story.json":
            return {
                "path": path,
                "type": "file",
                "content": json.dumps({"storyId": "story-demo", "status": "planning"}, ensure_ascii=False),
            }
        return {"path": path, "type": "file", "content": f"content for {path}"}

    async def fake_tool_execute(tool_id, args, *, user_id, agent_id, allowed_tool_ids, trace_id, parent_span_id=None):
        if tool_id == "file-list":
            return {
                "path": "stories/story-demo/chapters",
                "type": "dir",
                "items": [
                    {"path": "stories/story-demo/chapters/001.md", "type": "file"},
                    {"path": "stories/story-demo/chapters/002.md", "type": "file"},
                ],
            }
        if tool_id == "retrieval":
            return {
                "query": args["query"],
                "hits": [
                    {"documentId": "doc_1", "chunkId": "chunk_1", "score": 0.93, "scope": "story-lore"},
                ],
            }
        if tool_id == "file-mkdir":
            writebacks.append((tool_id, args))
            return {"path": f"stories/{args['path']}", "type": "dir", "created": True}
        if tool_id == "file-patch":
            writebacks.append((tool_id, args))
            return {"path": f"stories/{args['path']}", "type": "file", "patched": True, "mode": args["mode"]}
        if tool_id == "file-write":
            writebacks.append((tool_id, args))
            return {"path": f"stories/{args['path']}", "type": "file", "saved": True}
        raise AssertionError(f"unexpected tool: {tool_id}")

    async def fake_run_orchestrator(query: str, strategy: str = "auto", llm_config=None):
        captured["query"] = query
        captured["strategy"] = strategy
        return "agent", "story answer", 15

    import app.api.routes.unified as unified

    with patch.object(unified.deepagent_runtime_adapter._file_adapter, "read", side_effect=fake_file_read), patch.object(
        unified.deepagent_runtime_adapter._tool_adapter,
        "execute",
        side_effect=fake_tool_execute,
    ), patch("app.runtime.deepagent_adapter.run_orchestrator", side_effect=fake_run_orchestrator):
        resp = client.post(
            "/v1/agents/story-agent/invoke",
            json={
                "input": {"message": "Continue chapter two."},
                "context": {
                    "workspace": "story-demo",
                    "rag": {"enabled": True, "tenantId": "tenant-a", "scope": "story-lore"},
                },
            },
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["request"]["runtimeEngine"] == "deepagent"
    assert body["result"]["answer"] == "story answer"
    assert body["stepOutputs"]["memory"]["workspace"] == "story-demo"
    assert body["stepOutputs"]["retrieval"]["hits"][0]["scope"] == "story-lore"
    assert body["stepOutputs"]["writeback"]["mode"] == "append"
    assert body["stepOutputs"]["writeback"]["storyStateSaved"] is True
    assert body["stepOutputs"]["writeback"]["storyStatePath"] == "stories/story-demo/story.json"
    assert any(item["type"] == "prefetch_memory" for item in body["events"])
    assert any(item["type"] == "prefetch_retrieval" for item in body["events"])
    assert any(item["type"] == "writeback" for item in body["events"])
    assert captured["strategy"] == "agent"
    query = str(captured["query"])
    assert "Loaded workspace memory:" in query
    assert "content for story-demo/outline.md" in query
    assert "Retrieved knowledge:" in query
    assert "story-lore" in query
    story_writes = [args for tool_id, args in writebacks if tool_id == "file-write" and args["path"] == "story-demo/story.json"]
    assert story_writes
    persisted_story = json.loads(str(story_writes[0]["content"]))
    assert persisted_story["status"] == "drafting"
    assert persisted_story["lastAgentRun"]["writebackPath"] == "story-demo/notes.md"
    assert any(tool_id == "file-patch" and args["path"] == "story-demo/notes.md" for tool_id, args in writebacks)


def test_unified_stream_merges_step_tool_inputs_into_tool_args():
    client = TestClient(app)

    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, params=None):
            if "geocoding-api" in url:
                assert params["name"] == "Shanghai"
                return FakeResponse(
                    {
                        "results": [
                            {
                                "name": "Shanghai",
                                "country": "China",
                                "admin1": "Shanghai",
                                "latitude": 31.23,
                                "longitude": 121.47,
                            }
                        ]
                    }
                )
            return FakeResponse(
                {
                    "timezone": "Asia/Shanghai",
                    "current": {
                        "temperature_2m": 21.5,
                        "apparent_temperature": 22.0,
                        "wind_speed_10m": 12.4,
                        "weather_code": 1,
                    },
                    "current_units": {
                        "temperature_2m": "C",
                        "wind_speed_10m": "km/h",
                    },
                    "daily": {
                        "time": ["2026-03-21"],
                        "temperature_2m_max": [25.0],
                        "temperature_2m_min": [18.0],
                        "weather_code": [1],
                    },
                }
            )

    with patch("app.tools.builtin.httpx.AsyncClient", return_value=FakeAsyncClient()):
        resp = client.post(
            "/v1/unified/execute/stream",
            json={
                "requestId": "req-stream-tool-inputs",
                "tenantId": "tenant-a",
                "requestType": "chat",
                "messages": [{"role": "user", "content": "Need weather"}],
                "inputs": {
                    "confirmed": True,
                    "executionPlan": {
                        "planId": "plan-tool-inputs-1",
                        "mode": "agent",
                        "steps": [
                            {
                                "id": "s1",
                                "type": "llm",
                                "action": "Fetch weather details",
                                "tools": ["weather"],
                                "dependsOn": [],
                                "agent": "agent",
                            }
                        ],
                    },
                    "stepExecutions": [
                        {
                            "stepIndex": 0,
                            "agent": "agent",
                            "skills": [],
                            "tools": ["weather"],
                            "toolInputs": {"weather": {"location": "Shanghai"}},
                        }
                    ],
                },
            },
        )
    assert resp.status_code == 200
    text = resp.text
    assert '"toolId": "weather"' in text
    assert '"location": "Shanghai"' in text
