from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app


def _payload(query: str) -> dict:
    return {
        "requestId": "otie-req-1",
        "tenantId": "tenant-a",
        "requestType": "chat",
        "messages": [{"role": "user", "content": query}],
        "inputs": {},
        "metadata": {"source": "test"},
    }


def test_otie_intent_normalizes_request():
    client = TestClient(app)
    resp = client.post("/v1/otie/intent", json=_payload("Plan a Python learning roadmap."))
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["intent"]["requestId"] == "otie-req-1"
    assert body["intent"]["userQuery"] == "Plan a Python learning roadmap."
    assert body["intent"]["executionMode"] == "user_exec"


def test_otie_plan_returns_executable_steps():
    client = TestClient(app)
    resp = client.post("/v1/otie/plan", json={"request": _payload("Find skills for workflow automation.")})
    assert resp.status_code == 200
    body = resp.json()
    steps = body["executionPlan"]["steps"]
    assert len(steps) >= 2
    assert any(step["kind"] == "tool" and step["toolId"] == "find-skills" for step in steps)
    assert steps[-1]["kind"] == "respond"


def test_otie_plan_adds_weather_tool_for_weather_queries():
    client = TestClient(app)
    resp = client.post("/v1/otie/plan", json={"request": _payload("What's the weather in Shanghai today?")})
    assert resp.status_code == 200
    steps = resp.json()["executionPlan"]["steps"]
    weather_steps = [step for step in steps if step["kind"] == "tool" and step["toolId"] == "weather"]
    assert weather_steps
    assert weather_steps[0]["toolArgs"]["location"] == "Shanghai"


def test_otie_plan_adds_web_fetch_tool_for_page_queries():
    client = TestClient(app)
    resp = client.post(
        "/v1/otie/plan",
        json={"request": _payload("Read and summarize this page https://example.com/docs/getting-started")},
    )
    assert resp.status_code == 200
    steps = resp.json()["executionPlan"]["steps"]
    web_steps = [step for step in steps if step["kind"] == "tool" and step["toolId"] == "web-fetch"]
    assert web_steps
    assert web_steps[0]["toolArgs"]["url"] == "https://example.com/docs/getting-started"


def test_otie_run_executes_and_is_replayable():
    client = TestClient(app)
    resp = client.post("/v1/otie/run", json={"request": _payload("Find skills for workflow automation.")})
    assert resp.status_code == 200
    body = resp.json()
    run = body["run"]
    assert run["status"] == "completed"
    assert run["finalAnswer"]
    assert len(run["events"]) > 0

    fetch = client.get(f"/v1/otie/runs/{run['runId']}")
    assert fetch.status_code == 200
    fetched_run = fetch.json()["run"]
    assert fetched_run["runId"] == run["runId"]
    assert fetched_run["status"] == "completed"
    assert fetched_run["finalAnswer"] == run["finalAnswer"]


def test_otie_weather_tool_executes_with_mocked_http():
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

    request = _payload("What's the weather in Shanghai?")
    plan = {
        "intentId": "intent-weather",
        "mode": "agent",
        "status": "ready",
        "maxSteps": 4,
        "steps": [
            {
                "stepId": "s1",
                "kind": "tool",
                "action": "Fetch current weather for `Shanghai`.",
                "toolId": "weather",
                "toolArgs": {"location": "Shanghai", "query": request["messages"][0]["content"]},
                "dependsOn": [],
            },
            {
                "stepId": "s2",
                "kind": "respond",
                "action": "Compose the final response from completed step outputs.",
                "dependsOn": ["s1"],
                "agent": "agent",
            },
        ],
    }

    with patch("app.tools.builtin.httpx.AsyncClient", return_value=FakeAsyncClient()):
        resp = client.post("/v1/otie/run", json={"request": request, "plan": plan})

    assert resp.status_code == 200
    run = resp.json()["run"]
    assert run["status"] == "completed"
    assert run["stepOutputs"]["s1"]["location"]["name"] == "Shanghai"
    assert run["stepOutputs"]["s1"]["current"]["temperature"] == 21.5


def test_otie_tool_step_supports_schema_validation():
    client = TestClient(app)
    request = _payload("Find skills for workflow automation.")
    request["inputs"] = {"schemaValidationMode": "block"}
    intent = client.post("/v1/otie/intent", json=request).json()["intent"]
    plan = {
        "intentId": intent["intentId"],
        "mode": "agent",
        "status": "ready",
        "maxSteps": 4,
        "steps": [
            {
                "stepId": "s1",
                "kind": "tool",
                "action": "Search skills.",
                "dependsOn": [],
                "toolId": "find-skills",
                "toolArgs": {"query": "workflow"},
                "outputSchema": {
                    "type": "object",
                    "properties": {
                        "count": {"type": "number"},
                        "items": {"type": "array"},
                    },
                    "required": ["count", "items"],
                },
            },
            {
                "stepId": "s2",
                "kind": "respond",
                "action": "Compose the final response from completed step outputs.",
                "dependsOn": ["s1"],
                "agent": "agent",
            },
        ],
    }
    resp = client.post(
        "/v1/otie/run",
        json={"request": request, "plan": plan},
    )
    assert resp.status_code == 200
    run = resp.json()["run"]
    assert run["status"] == "completed"
    assert any(event["type"] == "schema_checked" and event["ok"] is True for event in run["events"])


def test_otie_run_requires_approval_for_high_risk_step():
    client = TestClient(app)
    intent = client.post("/v1/otie/intent", json=_payload("Please help with records.")).json()["intent"]
    plan = {
        "intentId": intent["intentId"],
        "mode": "agent",
        "status": "ready",
        "maxSteps": 3,
        "steps": [
            {
                "stepId": "s1",
                "kind": "reason",
                "action": "Delete all old records from the system.",
                "dependsOn": [],
                "agent": "agent",
            },
            {
                "stepId": "s2",
                "kind": "respond",
                "action": "Compose the final response from completed step outputs.",
                "dependsOn": ["s1"],
                "agent": "agent",
            },
        ],
    }
    resp = client.post("/v1/otie/run", json={"intent": intent, "plan": plan})
    assert resp.status_code == 200
    run = resp.json()["run"]
    assert run["status"] == "awaiting_approval"
    assert "approval" in run["finalAnswer"].lower()


def test_otie_run_blocks_denylisted_tool():
    client = TestClient(app)
    policy_resp = client.post(
        "/v1/capabilities/tools/policy",
        json={"toolId": "weather", "allowlisted": False, "denylisted": True},
    )
    assert policy_resp.status_code == 200
    request = _payload("What's the weather in Shanghai?")
    plan = {
        "intentId": "intent-weather-block",
        "mode": "agent",
        "status": "ready",
        "maxSteps": 3,
        "steps": [
            {
                "stepId": "s1",
                "kind": "tool",
                "action": "Fetch current weather for `Shanghai`.",
                "toolId": "weather",
                "toolArgs": {"location": "Shanghai"},
                "dependsOn": [],
            },
            {
                "stepId": "s2",
                "kind": "respond",
                "action": "Compose the final response from completed step outputs.",
                "dependsOn": ["s1"],
                "agent": "agent",
            },
        ],
    }
    resp = client.post("/v1/otie/run", json={"request": request, "plan": plan})
    assert resp.status_code == 200
    run = resp.json()["run"]
    assert run["status"] == "awaiting_approval"
    assert "not allowed" in run["finalAnswer"].lower()

    reset = client.post(
        "/v1/capabilities/tools/policy",
        json={"toolId": "weather", "denylisted": False},
    )
    assert reset.status_code == 200


def test_otie_run_blocks_tool_not_in_allowed_tool_ids():
    client = TestClient(app)
    request = _payload("What's the weather in Shanghai?")
    request["metadata"] = {"agentId": "policy-agent", "allowedToolIds": ["file-read"]}
    plan = {
        "intentId": "intent-weather-whitelist-block",
        "mode": "agent",
        "status": "ready",
        "maxSteps": 3,
        "steps": [
            {
                "stepId": "s1",
                "kind": "tool",
                "action": "Fetch current weather for `Shanghai`.",
                "toolId": "weather",
                "toolArgs": {"location": "Shanghai"},
                "dependsOn": [],
            },
            {
                "stepId": "s2",
                "kind": "respond",
                "action": "Compose the final response from completed step outputs.",
                "dependsOn": ["s1"],
                "agent": "agent",
            },
        ],
    }
    resp = client.post("/v1/otie/run", json={"request": request, "plan": plan})
    assert resp.status_code == 200
    run = resp.json()["run"]
    assert run["status"] == "awaiting_approval"
    assert "weather" in run["finalAnswer"].lower()
    assert "not allowed" in run["finalAnswer"].lower()


def test_otie_tool_invoke_endpoint_returns_args_and_result():
    client = TestClient(app)
    resp = client.post(
        "/v1/otie/tools/find-skills/invoke",
        json={"args": {"query": "workflow"}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["tool"]["id"] == "find-skills"
    assert body["args"]["query"] == "workflow"
    assert "result" in body
    assert "latencyMs" in body


def test_otie_web_fetch_tool_invocation_extracts_basic_page_content():
    client = TestClient(app)

    class FakeResponse:
        def __init__(self):
            self.text = """
                <html>
                    <head><title>Example Docs</title></head>
                    <body>
                        <main>
                            <h1>Getting Started</h1>
                            <p>Hello world.</p>
                            <script>console.log('ignore');</script>
                        </main>
                    </body>
                </html>
            """
            self.url = "https://example.com/docs/getting-started"
            self.status_code = 200
            self.headers = {"content-type": "text/html; charset=utf-8"}

        def raise_for_status(self):
            return None

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, headers=None):
            return FakeResponse()

    with patch("app.tools.builtin.httpx.AsyncClient", return_value=FakeAsyncClient()):
        resp = client.post(
            "/v1/otie/tools/web-fetch/invoke",
            json={"args": {"url": "https://example.com/docs/getting-started", "maxChars": 200}},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["tool"]["id"] == "web-fetch"
    assert body["result"]["title"] == "Example Docs"
    assert "Getting Started" in body["result"]["content"]
    assert "console.log" not in body["result"]["content"]
