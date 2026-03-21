from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app


@patch("app.api.routes.unified.clawhub_search_skills", new_callable=AsyncMock)
def test_clawhub_search_proxy_maps_results(mock_search: AsyncMock) -> None:
    mock_search.return_value = {
        "results": [
            {
                "slug": "weather",
                "displayName": "Weather",
                "summary": "Get weather",
                "score": 2.5,
            }
        ]
    }
    client = TestClient(app)
    resp = client.get("/v1/clawhub/search?q=test&limit=5")
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"][0]["id"] == "weather"
    assert body["items"][0]["name"] == "Weather"
    assert body["items"][0]["source"] == "clawhub"
    assert "registry" in body


def test_clawhub_register_adds_curated_skill() -> None:
    client = TestClient(app)
    resp = client.post(
        "/v1/clawhub/register",
        json={"slug": "demo-clawhub-skill", "displayName": "Demo", "summary": "x"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"

    caps = client.get("/v1/capabilities?pageSize=100").json()
    assert any(s["id"] == "demo-clawhub-skill" for s in caps["skills"])
