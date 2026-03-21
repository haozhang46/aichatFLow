from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app


@patch("app.api.routes.unified.build_clawhub_plan_suggestions", new_callable=AsyncMock)
def test_plan_response_includes_clawhub_suggestions(mock_build: AsyncMock) -> None:
    mock_build.return_value = [
        {
            "slug": "demo-skill",
            "name": "Demo Skill",
            "summary": "Does something safe",
            "score": 2.0,
            "riskLevel": "low",
            "recommendation": "adopt",
            "analysis": "测试分析",
        }
    ]
    client = TestClient(app)
    resp = client.post(
        "/v1/unified/plan",
        json={
            "requestId": "req-clawhub-plan",
            "tenantId": "tenant-a",
            "requestType": "chat",
            "messages": [{"role": "user", "content": "hello plan"}],
            "inputs": {"strategy": "workflow"},
        },
    )
    assert resp.status_code == 200
    out = resp.json()["output"]
    assert "clawhubPlanSuggestions" in out
    assert len(out["clawhubPlanSuggestions"]) == 1
    assert out["clawhubPlanSuggestions"][0]["slug"] == "demo-skill"
