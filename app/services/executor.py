from app.adapters.base import ProviderAdapter
from app.schemas.unified import UnifiedRequest, UnifiedResponse


class ExecutorService:
    def __init__(self, adapters: dict[str, ProviderAdapter]):
        self.adapters = adapters

    async def execute(self, req: UnifiedRequest, route, trace_id: str) -> UnifiedResponse:
        primary = self.adapters[route.primary_provider]
        result = await primary.execute(req, route.timeout_ms, trace_id)
        fallback_used = False
        if result.get("error") and route.fallback_provider != "none":
            fallback = self.adapters[route.fallback_provider]
            second = await fallback.execute(req, route.timeout_ms, trace_id)
            if not second.get("error"):
                result = second
                fallback_used = True
        return UnifiedResponse(
            requestId=req.request_id,
            provider=result["provider"],
            status="failed" if result.get("error") else "success",
            output=result.get("output"),
            error={"message": result["error"]} if result.get("error") else None,
            latencyMs=result["latency_ms"],
            traceId=trace_id,
            fallbackUsed=fallback_used,
        )
