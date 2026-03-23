from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


def test_files_api_supports_mkdir_and_patch_and_traces() -> None:
    client = TestClient(app)
    headers = {"Cookie": "user_id=tester"}
    admin_headers = {"Cookie": "role=admin"}
    acl = client.post(
        "/v1/files/acl",
        json={"userId": "tester", "path": "stories/demo-api/", "permissions": ["read", "write", "delete"]},
        headers=admin_headers,
    )
    assert acl.status_code == 200

    mkdir = client.post("/v1/files/mkdir", json={"path": "demo-api"}, headers=headers)
    assert mkdir.status_code == 200
    mkdir_body = mkdir.json()
    assert mkdir_body["type"] == "dir"
    assert mkdir_body["created"] is True

    write = client.put("/v1/files", json={"path": "demo-api/note.md", "content": "# Title"}, headers=headers)
    assert write.status_code == 200

    patch = client.patch(
        "/v1/files",
        json={"path": "demo-api/note.md", "content": "\n## Next", "mode": "append"},
        headers=headers,
    )
    assert patch.status_code == 200
    patch_body = patch.json()
    assert patch_body["patched"] is True
    assert patch_body["mode"] == "append"

    read = client.get("/v1/files", params={"path": "demo-api/note.md"}, headers=headers)
    assert read.status_code == 200
    assert "## Next" in read.json()["content"]

    trace = client.get(f"/v1/traces/{patch_body['traceId']}/events")
    assert trace.status_code == 200
    assert "file_patch" in [item["type"] for item in trace.json()["events"]]

    delete_file = client.delete("/v1/files", params={"path": "demo-api/note.md"}, headers=headers)
    assert delete_file.status_code == 200
    delete_dir = client.delete("/v1/files", params={"path": "demo-api"}, headers=headers)
    assert delete_dir.status_code == 200
    client.delete("/v1/files/acl", params={"userId": "tester", "path": "stories/demo-api/"}, headers=admin_headers)


def test_file_tools_include_mkdir_and_patch() -> None:
    client = TestClient(app)
    resp = client.get("/v1/otie/tools")
    assert resp.status_code == 200
    tool_ids = {item["id"] for item in resp.json()["items"]}
    assert "file-mkdir" in tool_ids
    assert "file-patch" in tool_ids


def test_file_patch_tool_executes_with_acl_and_updates_content() -> None:
    client = TestClient(app)
    headers = {"Cookie": "user_id=tester"}
    admin_headers = {"Cookie": "role=admin"}
    acl = client.post(
        "/v1/files/acl",
        json={"userId": "tester", "path": "stories/demo-tool/", "permissions": ["read", "write", "delete"]},
        headers=admin_headers,
    )
    assert acl.status_code == 200

    create_dir = client.post("/v1/files/mkdir", json={"path": "demo-tool"}, headers=headers)
    assert create_dir.status_code == 200
    create_file = client.put("/v1/files", json={"path": "demo-tool/note.md", "content": "hello"}, headers=headers)
    assert create_file.status_code == 200

    invoke = client.post(
        "/v1/otie/tools/file-patch/invoke",
        json={"args": {"path": "demo-tool/note.md", "content": " world", "mode": "append"}},
        headers=headers,
    )
    assert invoke.status_code == 200
    body = invoke.json()
    assert body["status"] == "success"
    assert body["result"]["patched"] is True

    read = client.get("/v1/files", params={"path": "demo-tool/note.md"}, headers=headers)
    assert read.status_code == 200
    assert read.json()["content"] == "hello world"

    client.delete("/v1/files", params={"path": "demo-tool/note.md"}, headers=headers)
    client.delete("/v1/files", params={"path": "demo-tool"}, headers=headers)
    client.delete("/v1/files/acl", params={"userId": "tester", "path": "stories/demo-tool/"}, headers=admin_headers)
