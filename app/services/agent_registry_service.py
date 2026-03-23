from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import re
from typing import Any
from uuid import uuid4

from app.services.schema_validation import validate_against_schema


class AgentRegistryService:
    def __init__(self) -> None:
        root = Path(__file__).resolve().parents[2]
        self._root = root
        self._legacy_agent_dir = root / "specs" / "main" / "agents"
        self._registry_dir = root / "data" / "registry" / "agents"
        self._draft_dir = root / "data" / "drafts" / "agents"
        self._schema_path = root / "specs" / "main" / "contracts" / "agent-spec.schema.json"
        self._legacy_agent_dir.mkdir(parents=True, exist_ok=True)
        self._registry_dir.mkdir(parents=True, exist_ok=True)
        self._draft_dir.mkdir(parents=True, exist_ok=True)

    def list_agents(self) -> list[dict[str, Any]]:
        return [self._to_capability_view(item) for item in self.list_registered_agents()]

    def list_registered_agents(self) -> list[dict[str, Any]]:
        items: dict[str, dict[str, Any]] = {}
        for path in sorted(self._legacy_agent_dir.glob("*.json")):
            record = self._read_legacy_spec(path)
            if record is not None:
                items[record["id"]] = record
        for path in sorted(self._registry_dir.glob("*.json")):
            record = self._read_registry_record(path)
            if record is not None:
                items[record["id"]] = record
        return [items[key] for key in sorted(items)]

    def get_agent(self, agent_id: str) -> dict[str, Any] | None:
        record = self.get_agent_record(agent_id)
        if record is None:
            return None
        return self._to_capability_view(record)

    def get_agent_record(self, agent_id: str) -> dict[str, Any] | None:
        normalized_id = self._normalize_id(agent_id)
        if not normalized_id:
            return None
        registry_path = self._registry_dir / f"{normalized_id}.json"
        if registry_path.exists():
            return self._read_registry_record(registry_path)
        legacy_path = self._legacy_agent_dir / f"{normalized_id}.json"
        if legacy_path.exists():
            return self._read_legacy_spec(legacy_path)
        return None

    def register_agent(self, spec: dict[str, Any], *, source_kind: str = "manual") -> dict[str, Any]:
        validation = validate_against_schema(spec, self._load_schema())
        if not validation.ok:
            return {"ok": False, "message": validation.error or "invalid agent spec"}
        agent_id = self._normalize_id(str(spec.get("id") or ""))
        if not agent_id:
            return {"ok": False, "message": "agent id is invalid"}
        now = datetime.utcnow().isoformat()
        path = self._registry_dir / f"{agent_id}.json"
        existing = self._read_registry_record(path) if path.exists() else None
        created_at = str((existing or {}).get("createdAt") or now)
        record = {
            **spec,
            "id": agent_id,
            "status": "registered",
            "source": {"type": "custom", "path": str(path.relative_to(self._root))},
            "lifecycle": {
                "entityType": "agent",
                "entityId": agent_id,
                "version": str(spec.get("version") or "0.1.0"),
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
        return {"ok": True, "agent": record}

    def create_draft(self, prompt: str) -> dict[str, Any]:
        text = str(prompt or "").strip()
        if not text:
            return {"ok": False, "message": "prompt is required"}
        draft_id = self._normalize_id(f"draft-agent-{uuid4().hex[:8]}")
        spec = self._build_draft_spec(text, draft_id)
        validation = validate_against_schema(spec, self._load_schema())
        now = datetime.utcnow().isoformat()
        lifecycle = {
            "entityType": "agent",
            "entityId": str(spec.get("id") or draft_id),
            "version": str(spec.get("version") or "0.1.0"),
            "state": "validated" if validation.ok else "validation_failed",
            "validation": {
                "status": "passed" if validation.ok else "failed",
                "errors": [] if validation.ok else [{"code": "schema_validation_failed", "message": validation.error or "invalid agent draft"}],
            },
            "review": {"status": "pending"},
            "source": {"kind": "llm_draft", "draftId": draft_id},
            "createdAt": now,
            "updatedAt": now,
        }
        record = {
            "draftId": draft_id,
            "prompt": text,
            "draft": spec,
            "status": "draft",
            "lifecycle": lifecycle,
            "createdAt": now,
            "updatedAt": now,
        }
        path = self._draft_dir / f"{draft_id}.json"
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"ok": validation.ok, "draft": record, "message": validation.error if not validation.ok else "success"}

    def publish_agent(self, agent_id: str) -> dict[str, Any]:
        normalized_id = self._normalize_id(agent_id)
        path = self._registry_dir / f"{normalized_id}.json"
        record = self._read_registry_record(path) if path.exists() else None
        if record is None:
            return {"ok": False, "message": f"agent `{normalized_id}` not found in registry"}
        now = datetime.utcnow().isoformat()
        lifecycle = dict(record.get("lifecycle") or {})
        state = str(lifecycle.get("state") or "")
        if state not in {"registered", "publish_pending", "published"}:
            return {"ok": False, "message": f"agent `{normalized_id}` cannot be published from state `{state}`"}
        lifecycle["state"] = "published"
        lifecycle["updatedAt"] = now
        lifecycle["publishedAt"] = now
        record["status"] = "published"
        record["updatedAt"] = now
        record["publishedAt"] = now
        record["lifecycle"] = lifecycle
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"ok": True, "agent": record}

    def create_agent(self, agent_id: str, label: str, description: str) -> dict[str, Any]:
        normalized_id = self._normalize_id(agent_id)
        if not normalized_id:
            return {"ok": False, "message": "agent id is invalid"}
        existing = self.get_agent_record(normalized_id)
        if existing is not None:
            return {"ok": False, "message": f"agent `{normalized_id}` already exists"}
        spec = {
            "id": normalized_id,
            "name": label.strip() or normalized_id,
            "description": description.strip() or f"Custom agent `{normalized_id}`",
            "version": "0.1.0",
            "systemPrompt": (
                f"You are `{label.strip() or normalized_id}`. "
                "Help the user complete the request accurately and concisely."
            ),
            "availableTools": [],
            "runtime": {"mode": "agent", "engine": "otie", "maxSteps": 8},
            "memory": {"type": "none"},
            "policy": {"requiresUserContext": False},
        }
        return self.register_agent(spec)

    def delete_agent(self, agent_id: str) -> dict[str, Any]:
        normalized_id = self._normalize_id(agent_id)
        path = self._registry_dir / f"{normalized_id}.json"
        if not path.exists():
            return {"ok": False, "message": f"agent `{normalized_id}` not found"}
        path.unlink()
        return {"ok": True}

    def _load_schema(self) -> dict[str, Any]:
        try:
            return json.loads(self._schema_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _read_registry_record(self, path: Path) -> dict[str, Any] | None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        if not isinstance(data, dict):
            return None
        return data

    def _read_legacy_spec(self, path: Path) -> dict[str, Any] | None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        if not isinstance(data, dict):
            return None
        agent_id = self._normalize_id(str(data.get("id") or path.stem))
        if not agent_id:
            return None
        now = datetime.utcnow().isoformat()
        return {
            "id": agent_id,
            "name": str(data.get("name") or data.get("label") or agent_id),
            "label": str(data.get("label") or data.get("name") or agent_id),
            "description": str(data.get("description") or ""),
            "version": str(data.get("version") or "0.1.0"),
            "systemPrompt": str(data.get("systemPrompt") or ""),
            "availableTools": data.get("availableTools") if isinstance(data.get("availableTools"), list) else [],
            "runtime": data.get("runtime") if isinstance(data.get("runtime"), dict) else {"mode": "agent", "engine": "otie", "maxSteps": 8},
            "memory": data.get("memory") if isinstance(data.get("memory"), dict) else {"type": "none"},
            "policy": data.get("policy") if isinstance(data.get("policy"), dict) else {"requiresUserContext": False},
            "status": str(data.get("status") or "published"),
            "source": {"type": "core", "path": str(path.relative_to(self._root))},
            "lifecycle": {
                "entityType": "agent",
                "entityId": agent_id,
                "version": str(data.get("version") or "0.1.0"),
                "state": str(data.get("status") or "published"),
                "validation": {"status": "passed", "errors": []},
                "review": {"status": "not_required"},
                "source": {"kind": "manual"},
                "createdAt": str(data.get("createdAt") or now),
                "updatedAt": str(data.get("updatedAt") or now),
                "publishedAt": str(data.get("publishedAt") or now),
            },
            "createdAt": str(data.get("createdAt") or now),
            "updatedAt": str(data.get("updatedAt") or now),
            "publishedAt": str(data.get("publishedAt") or now),
        }

    def _to_capability_view(self, record: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(record.get("id") or ""),
            "label": str(record.get("label") or record.get("name") or ""),
            "name": str(record.get("name") or record.get("label") or ""),
            "description": str(record.get("description") or ""),
            "systemPrompt": str(record.get("systemPrompt") or ""),
            "version": str(record.get("version") or "0.1.0"),
            "status": str(record.get("status") or "registered"),
            "source": str((record.get("source") or {}).get("type") or "custom"),
            "available": str(record.get("status") or "") == "published",
        }

    def _normalize_id(self, value: str) -> str:
        lowered = value.strip().lower()
        lowered = re.sub(r"\s+", "-", lowered)
        lowered = re.sub(r"[^a-z0-9\-_]+", "", lowered)
        return lowered[:64]

    def _build_draft_spec(self, prompt: str, draft_id: str) -> dict[str, Any]:
        title = self._title_from_prompt(prompt, fallback="Draft Agent")
        return {
            "id": draft_id.replace("draft-agent-", "agent-")[:64],
            "name": title,
            "description": prompt[:1000],
            "version": "0.1.0",
            "systemPrompt": f"You are `{title}`. Fulfill the user's request based on this brief:\n{prompt}",
            "availableTools": [],
            "runtime": {"mode": "agent", "engine": "otie", "maxSteps": 8},
            "memory": {"type": "none"},
            "policy": {"requiresUserContext": True},
        }

    def _title_from_prompt(self, prompt: str, *, fallback: str) -> str:
        words = [part for part in re.split(r"\s+", prompt.strip()) if part]
        if not words:
            return fallback
        return " ".join(words[:6])[:120]
