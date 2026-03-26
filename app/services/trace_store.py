"""Trace storage with pluggable backend: RPC first, local JSONL fallback."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Protocol

import httpx

from app.core.config import settings


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


_SENSITIVE_KEYS = {
    "apikey",
    "api_key",
    "authorization",
    "token",
    "access_token",
    "refresh_token",
    "secret",
    "password",
}


def _redact_string(value: str) -> str:
    text = value.strip()
    if not text:
        return value
    if len(text) <= 8:
        return "***REDACTED***"
    return f"{text[:4]}***{text[-4:]}"


def sanitize_sensitive_data(value: Any, parent_key: str | None = None) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            normalized_key = str(key).strip()
            sanitized[normalized_key] = sanitize_sensitive_data(item, normalized_key)
        return sanitized
    if isinstance(value, list):
        return [sanitize_sensitive_data(item, parent_key) for item in value]
    if isinstance(value, tuple):
        return [sanitize_sensitive_data(item, parent_key) for item in value]
    if parent_key and parent_key.strip().lower() in _SENSITIVE_KEYS:
        return _redact_string(str(value))
    return value


class TraceBackend(Protocol):
    def append(self, trace_id: str, event: dict[str, Any]) -> None:
        ...

    def read_trace(self, trace_id: str) -> list[dict[str, Any]]:
        ...

    def find_by_request_id(self, request_id: str, limit: int = 20) -> list[str]:
        ...


class FileTraceBackend:
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


class RpcTraceBackend:
    def __init__(self, base_url: str, timeout_seconds: float = 5.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    def append(self, trace_id: str, event: dict[str, Any]) -> None:
        payload = {"traceId": trace_id, "event": {"ts": _utc_now_iso(), "traceId": trace_id, **event}}
        with httpx.Client(timeout=self._timeout_seconds) as client:
            response = client.post(f"{self._base_url}/v1/traces/append", json=payload)
            response.raise_for_status()

    def read_trace(self, trace_id: str) -> list[dict[str, Any]]:
        with httpx.Client(timeout=self._timeout_seconds) as client:
            response = client.get(f"{self._base_url}/v1/traces/{trace_id}/events")
            if response.status_code == 404:
                return []
            response.raise_for_status()
            payload = response.json()
        events = payload.get("events") if isinstance(payload, dict) else None
        if not isinstance(events, list):
            return []
        return [item for item in events if isinstance(item, dict)]

    def find_by_request_id(self, request_id: str, limit: int = 20) -> list[str]:
        with httpx.Client(timeout=self._timeout_seconds) as client:
            response = client.get(
                f"{self._base_url}/v1/traces",
                params={"requestId": request_id, "limit": limit},
            )
            response.raise_for_status()
            payload = response.json()
        trace_ids = payload.get("traceIds") if isinstance(payload, dict) else None
        if not isinstance(trace_ids, list):
            return []
        return [str(item) for item in trace_ids if str(item).strip()]


class TraceStore:
    def __init__(self, base_dir: Optional[Path] = None) -> None:
        self._backend = self._build_backend(base_dir=base_dir)

    def append(self, trace_id: str, event: dict[str, Any]) -> None:
        self._backend.append(trace_id, sanitize_sensitive_data(event))

    def read_trace(self, trace_id: str) -> list[dict[str, Any]]:
        return self._backend.read_trace(trace_id)

    def find_by_request_id(self, request_id: str, limit: int = 20) -> list[str]:
        return self._backend.find_by_request_id(request_id, limit=limit)

    def backend_kind(self) -> str:
        return "rpc" if isinstance(self._backend, RpcTraceBackend) else "file"

    def _build_backend(self, *, base_dir: Optional[Path]) -> TraceBackend:
        rpc_url = settings.trace_rpc_url.strip()
        if rpc_url:
            return RpcTraceBackend(rpc_url, timeout_seconds=float(settings.trace_rpc_timeout_seconds))
        return FileTraceBackend(base_dir=base_dir)
