from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class FileAclService:
    def __init__(self) -> None:
        root = Path(__file__).resolve().parents[2]
        self._data_dir = root / "data"
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._acl_path = self._data_dir / "file_acl.json"
        if not self._acl_path.exists():
            self._acl_path.write_text(
                json.dumps({"rules": []}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        else:
            self._remove_legacy_wildcard_rule()

    def is_allowed(self, user_id: str, path: str, action: str) -> bool:
        normalized_path = self._normalize_acl_path(path)
        if not user_id.strip():
            return False
        for rule in self._read_rules():
            rule_user = str(rule.get("userId") or "").strip()
            if rule_user not in {"*", user_id}:
                continue
            if action not in {str(item).strip() for item in (rule.get("permissions") or []) if str(item).strip()}:
                continue
            rule_path = self._normalize_acl_path(str(rule.get("path") or ""))
            if self._path_matches(rule_path, normalized_path):
                return True
        return False

    def list_rules(self, *, user_id: str | None = None, path_prefix: str | None = None) -> list[dict[str, Any]]:
        rules = self._read_rules()
        if user_id:
            rules = [rule for rule in rules if str(rule.get("userId") or "").strip() == user_id]
        if path_prefix:
            prefix = self._normalize_acl_path(path_prefix)
            rules = [rule for rule in rules if self._normalize_acl_path(str(rule.get("path") or "")).startswith(prefix)]
        return rules

    def upsert_rule(self, *, user_id: str, path: str, permissions: list[str]) -> dict[str, Any]:
        normalized_path = self._normalize_acl_path(path)
        normalized_permissions = sorted({item for item in permissions if item in {"read", "write", "delete"}})
        if not user_id.strip():
            raise ValueError("userId is required")
        if not normalized_path:
            raise ValueError("path is required")
        if not normalized_permissions:
            raise ValueError("permissions are required")
        rules = self._read_rules()
        replaced = False
        for index, rule in enumerate(rules):
            if (
                str(rule.get("userId") or "").strip() == user_id
                and self._normalize_acl_path(str(rule.get("path") or "")) == normalized_path
            ):
                rules[index] = {"userId": user_id, "path": normalized_path, "permissions": normalized_permissions}
                replaced = True
                break
        if not replaced:
            rules.append({"userId": user_id, "path": normalized_path, "permissions": normalized_permissions})
        self._write_rules(rules)
        return {"userId": user_id, "path": normalized_path, "permissions": normalized_permissions}

    def delete_rule(self, *, user_id: str, path: str) -> bool:
        normalized_path = self._normalize_acl_path(path)
        rules = self._read_rules()
        next_rules = [
            rule
            for rule in rules
            if not (
                str(rule.get("userId") or "").strip() == user_id
                and self._normalize_acl_path(str(rule.get("path") or "")) == normalized_path
            )
        ]
        if len(next_rules) == len(rules):
            return False
        self._write_rules(next_rules)
        return True

    def _read_rules(self) -> list[dict[str, Any]]:
        try:
            payload = json.loads(self._acl_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        rules = payload.get("rules") if isinstance(payload, dict) else payload
        if not isinstance(rules, list):
            return []
        return [item for item in rules if isinstance(item, dict)]

    def _write_rules(self, rules: list[dict[str, Any]]) -> None:
        self._acl_path.write_text(json.dumps({"rules": rules}, ensure_ascii=False, indent=2), encoding="utf-8")

    def _normalize_acl_path(self, path: str) -> str:
        value = path.strip().replace("\\", "/").strip("/")
        if not value:
            return ""
        return f"{value}/" if not Path(value).suffix else value

    def _path_matches(self, rule_path: str, requested_path: str) -> bool:
        if not rule_path:
            return False
        if requested_path == rule_path:
            return True
        if rule_path.endswith("/"):
            return requested_path.startswith(rule_path)
        return requested_path == rule_path or requested_path.startswith(f"{rule_path}/")

    def _remove_legacy_wildcard_rule(self) -> None:
        rules = self._read_rules()
        filtered = [
            rule
            for rule in rules
            if not (
                str(rule.get("userId") or "").strip() == "*"
                and self._normalize_acl_path(str(rule.get("path") or "")) == "stories/"
            )
        ]
        if len(filtered) != len(rules):
            self._write_rules(filtered)
