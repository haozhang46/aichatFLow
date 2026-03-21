import time

import httpx

from app.adapters.base import ProviderAdapter, ProviderResult
from app.schemas.unified import UnifiedRequest


class DifyAdapter(ProviderAdapter):
    provider = "dify"

    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url
        self.api_key = api_key

    async def execute(self, req: UnifiedRequest, timeout_ms: int, trace_id: str) -> ProviderResult:
        start = time.monotonic()
        path = "/v1/workflows/run" if req.request_type == "workflow" else "/v1/chat-messages"
        try:
            async with httpx.AsyncClient(timeout=timeout_ms / 1000) as client:
                resp = await client.post(
                    f"{self.base_url}{path}",
                    json={
                        "query": (req.messages or [{"content": ""}])[0].get("content", ""),
                        "inputs": req.inputs or {},
                        "workflow_id": req.workflow_id,
                    },
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                resp.raise_for_status()
                return ProviderResult(
                    provider=self.provider,
                    output=resp.json(),
                    error=None,
                    latency_ms=int((time.monotonic() - start) * 1000),
                )
        except Exception as exc:
            return ProviderResult(
                provider=self.provider,
                output=None,
                error=str(exc),
                latency_ms=int((time.monotonic() - start) * 1000),
            )
