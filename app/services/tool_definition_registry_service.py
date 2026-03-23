from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import re
from typing import Any
from uuid import uuid4

from app.services.schema_validation import validate_against_schema


class ToolDefinitionRegistryService:
    def __init__(self) -> None:
        root = Path(__file__).resolve().parents[2]
        self._root = root
        self._registry_dir = root / "data" / "registry" / "tools"
        self._draft_dir = root / "data" / "drafts" / "tools"
        self._schema_path = root / "specs" / "main" / "contracts" / "tool-manifest.schema.json"
        self._registry_dir.mkdir(parents=True, exist_ok=True)
        self._draft_dir.mkdir(parents=True, exist_ok=True)

    def list_tools(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for path in sorted(self._registry_dir.glob("*.json")):
            record = self._read_record(path)
            if record is not None:
                items.append(record)
        return items

    def get_tool(self, tool_id: str) -> dict[str, Any] | None:
        normalized_id = self._normalize_id(tool_id)
        if not normalized_id:
            return None
        path = self._registry_dir / f"{normalized_id}.json"
        if not path.exists():
            return None
        return self._read_record(path)

    def register_tool(self, manifest: dict[str, Any], *, source_kind: str = "manual") -> dict[str, Any]:
        validation = validate_against_schema(manifest, self._load_schema())
        if not validation.ok:
            return {"ok": False, "message": validation.error or "invalid tool manifest"}
        tool_id = self._normalize_id(str(manifest.get("id") or ""))
        if not tool_id:
            return {"ok": False, "message": "tool id is invalid"}
        now = datetime.utcnow().isoformat()
        path = self._registry_dir / f"{tool_id}.json"
        existing = self._read_record(path) if path.exists() else None
        created_at = str((existing or {}).get("createdAt") or now)
        record = {
            **manifest,
            "id": tool_id,
            "status": "registered",
            "source": {"type": "custom", "path": str(path.relative_to(self._root))},
            "lifecycle": {
                "entityType": "tool",
                "entityId": tool_id,
                "version": str(manifest.get("version") or "0.1.0"),
                "state": "registered",
                "validation": {"status": "passed", "errors": []},
                "review": {"status": "pending" if source_kind == "llm_draft" else "not_required"},
                "source": {"kind": source_kind},
                "createdAt": created_at,
                "updatedAt": now,
            },
            "createdAt": created_at,
            "updatedAt": now,
        }
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"ok": True, "tool": record}

    def create_draft(self, prompt: str) -> dict[str, Any]:
        text = str(prompt or "").strip()
        if not text:
            return {"ok": False, "message": "prompt is required"}
        draft_id = self._normalize_id(f"draft-tool-{uuid4().hex[:8]}")
        manifest = self._build_draft_manifest(text, draft_id)
        validation = validate_against_schema(manifest, self._load_schema())
        now = datetime.utcnow().isoformat()
        lifecycle = {
            "entityType": "tool",
            "entityId": str(manifest.get("id") or draft_id),
            "version": str(manifest.get("version") or "0.1.0"),
            "state": "validated" if validation.ok else "validation_failed",
            "validation": {
                "status": "passed" if validation.ok else "failed",
                "errors": [] if validation.ok else [{"code": "schema_validation_failed", "message": validation.error or "invalid tool draft"}],
            },
            "review": {"status": "pending"},
            "source": {"kind": "llm_draft", "draftId": draft_id},
            "createdAt": now,
            "updatedAt": now,
        }
        record = {
            "draftId": draft_id,
            "prompt": text,
            "draft": manifest,
            "status": "draft",
            "lifecycle": lifecycle,
            "createdAt": now,
            "updatedAt": now,
        }
        path = self._draft_dir / f"{draft_id}.json"
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"ok": validation.ok, "draft": record, "message": validation.error if not validation.ok else "success"}

    def publish_tool(self, tool_id: str) -> dict[str, Any]:
        normalized_id = self._normalize_id(tool_id)
        path = self._registry_dir / f"{normalized_id}.json"
        record = self._read_record(path) if path.exists() else None
        if record is None:
            return {"ok": False, "message": f"tool `{normalized_id}` not found in registry"}
        now = datetime.utcnow().isoformat()
        lifecycle = dict(record.get("lifecycle") or {})
        state = str(lifecycle.get("state") or "")
        if state not in {"registered", "publish_pending", "published"}:
            return {"ok": False, "message": f"tool `{normalized_id}` cannot be published from state `{state}`"}
        lifecycle["state"] = "published"
        lifecycle["updatedAt"] = now
        lifecycle["publishedAt"] = now
        record["status"] = "published"
        record["updatedAt"] = now
        record["publishedAt"] = now
        record["lifecycle"] = lifecycle
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"ok": True, "tool": record}

    def _load_schema(self) -> dict[str, Any]:
        try:
            return json.loads(self._schema_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _read_record(self, path: Path) -> dict[str, Any] | None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        if not isinstance(data, dict):
            return None
        return data

    def _build_draft_manifest(self, prompt: str, draft_id: str) -> dict[str, Any]:
        title = self._title_from_prompt(prompt, fallback="Draft Tool")
        return {
            "id": draft_id.replace("draft-tool-", "tool-")[:64],
            "name": title,
            "description": prompt[:1000],
            "version": "0.1.0",
            "kind": "builtin",
            "category": "custom",
            "inputSchema": {"type": "object", "additionalProperties": True},
            "outputSchema": {"type": "object", "additionalProperties": True},
            "uiSchema": {"layout": "form", "fields": []},
            "auth": {"mode": "user", "requiresCookie": True},
            "policy": {"riskLevel": "medium", "allowAgents": []},
        }

    def _normalize_id(self, value: str) -> str:
        lowered = value.strip().lower()
        lowered = re.sub(r"\s+", "-", lowered)
        lowered = re.sub(r"[^a-z0-9\-_]+", "", lowered)
        return lowered[:64]

    def _title_from_prompt(self, prompt: str, *, fallback: str) -> str:
        words = [part for part in re.split(r"\s+", prompt.strip()) if part]
        if not words:
            return fallback
        return " ".join(words[:6])[:120]
