"""Append-only approval audit log."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ApprovalStore:
    def __init__(self, base_dir: Optional[Path] = None) -> None:
        root = Path(__file__).resolve().parents[2]
        self._dir = base_dir or (root / "data" / "approvals")
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / "audit.jsonl"

    def append(
        self,
        *,
        trace_id: str,
        request_id: str,
        tenant_id: str,
        step_id: str,
        approved: bool,
        meta: Optional[dict[str, Any]] = None,
    ) -> None:
        rec = {
            "ts": _utc_now_iso(),
            "traceId": trace_id,
            "requestId": request_id,
            "tenantId": tenant_id,
            "stepId": step_id,
            "approved": approved,
            "meta": meta or {},
        }
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def list_for_trace(self, trace_id: str, limit: int = 200) -> list[dict[str, Any]]:
        if not self._path.is_file():
            return []
        out: list[dict[str, Any]] = []
        with self._path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if data.get("traceId") == trace_id:
                    out.append(data)
        return out[-limit:]
