from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from app.services.policy_engine import PolicyEngine


class ToolPolicyService:
    def __init__(self, policy_engine: PolicyEngine, base_dir: Optional[Path] = None) -> None:
        self._policy_engine = policy_engine
        root = Path(__file__).resolve().parents[2]
        self._dir = base_dir or (root / "data" / "otie")
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / "tool_policy.json"
        self._state = {"allowlist": [], "denylist": []}
        self._load()
        self._apply()

    def _load(self) -> None:
        if not self._path.is_file():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        allow = data.get("allowlist")
        deny = data.get("denylist")
        if isinstance(allow, list):
            self._state["allowlist"] = sorted({str(x).strip() for x in allow if str(x).strip()})
        if isinstance(deny, list):
            self._state["denylist"] = sorted({str(x).strip() for x in deny if str(x).strip()})

    def _save(self) -> None:
        self._path.write_text(json.dumps(self._state, ensure_ascii=False, indent=2), encoding="utf-8")

    def _apply(self) -> None:
        allow = set(self._state["allowlist"])
        deny = set(self._state["denylist"])
        self._policy_engine.allow_tools = allow if allow else None
        self._policy_engine.deny_tools = deny if deny else None

    def snapshot(self) -> dict[str, list[str]]:
        return {
            "allowlist": list(self._state["allowlist"]),
            "denylist": list(self._state["denylist"]),
        }

    def status_for(self, tool_id: str) -> dict[str, bool]:
        return {
            "allowlisted": tool_id in self._state["allowlist"],
            "denylisted": tool_id in self._state["denylist"],
        }

    def set_policy(
        self,
        tool_id: str,
        *,
        allowlisted: Optional[bool] = None,
        denylisted: Optional[bool] = None,
    ) -> dict[str, object]:
        allow = set(self._state["allowlist"])
        deny = set(self._state["denylist"])
        if allowlisted is not None:
            if allowlisted:
                allow.add(tool_id)
            else:
                allow.discard(tool_id)
        if denylisted is not None:
            if denylisted:
                deny.add(tool_id)
            else:
                deny.discard(tool_id)
        self._state["allowlist"] = sorted(allow)
        self._state["denylist"] = sorted(deny)
        self._save()
        self._apply()
        return {
            "ok": True,
            "toolId": tool_id,
            "allowlisted": tool_id in allow,
            "denylisted": tool_id in deny,
            "policy": self.snapshot(),
        }
