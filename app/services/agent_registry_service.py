from __future__ import annotations

from pathlib import Path
import json
import re
from typing import Any


class AgentRegistryService:
    def __init__(self) -> None:
        root = Path(__file__).resolve().parents[2]
        self._agent_dir = root / "specs" / "main" / "agents"
        self._agent_dir.mkdir(parents=True, exist_ok=True)

    def list_agents(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for path in sorted(self._agent_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            items.append(
                {
                    "id": str(data.get("id", path.stem)),
                    "label": str(data.get("label", path.stem)),
                    "description": str(data.get("description", "")),
                    "source": "self-built",
                    "available": True,
                }
            )
        return items

    def create_agent(self, agent_id: str, label: str, description: str) -> dict[str, Any]:
        normalized_id = self._normalize_id(agent_id)
        if not normalized_id:
            return {"ok": False, "message": "agent id is invalid"}
        path = self._agent_dir / f"{normalized_id}.json"
        if path.exists():
            return {"ok": False, "message": f"agent `{normalized_id}` already exists"}
        payload = {"id": normalized_id, "label": label.strip() or normalized_id, "description": description.strip()}
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"ok": True, "agent": payload}

    def delete_agent(self, agent_id: str) -> dict[str, Any]:
        normalized_id = self._normalize_id(agent_id)
        path = self._agent_dir / f"{normalized_id}.json"
        if not path.exists():
            return {"ok": False, "message": f"agent `{normalized_id}` not found"}
        path.unlink()
        return {"ok": True}

    def _normalize_id(self, value: str) -> str:
        lowered = value.strip().lower()
        lowered = re.sub(r"\s+", "-", lowered)
        lowered = re.sub(r"[^a-z0-9\-_]+", "", lowered)
        return lowered[:64]
