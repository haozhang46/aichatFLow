"""Append-only JSONL trace storage for execution events."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TraceStore:
    def __init__(self, base_dir: Optional[Path] = None) -> None:
        root = Path(__file__).resolve().parents[2]
        self._dir = base_dir or (root / "data" / "traces")
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, trace_id: str) -> Path:
        safe = "".join(c for c in trace_id if c.isalnum() or c in ("_", "-"))[:128]
        if not safe:
            safe = "unknown"
        return self._dir / f"{safe}.jsonl"

    def append(self, trace_id: str, event: dict[str, Any]) -> None:
        line = json.dumps({"ts": _utc_now_iso(), "traceId": trace_id, **event}, ensure_ascii=False)
        path = self._path(trace_id)
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def read_trace(self, trace_id: str) -> list[dict[str, Any]]:
        path = self._path(trace_id)
        if not path.is_file():
            return []
        out: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return out

    def find_by_request_id(self, request_id: str, limit: int = 20) -> list[str]:
        """Scan trace files for matching requestId (MVP: linear scan, small dev volumes)."""
        matches: list[str] = []
        for path in sorted(self._dir.glob("*.jsonl"), reverse=True):
            try:
                with path.open("r", encoding="utf-8") as f:
                    head = f.readline()
                if not head:
                    continue
                data = json.loads(head)
                if data.get("requestId") == request_id:
                    matches.append(str(data.get("traceId") or path.stem))
                    if len(matches) >= limit:
                        break
            except (OSError, json.JSONDecodeError):
                continue
        return matches
