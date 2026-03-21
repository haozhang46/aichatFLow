from abc import ABC, abstractmethod
from typing import Any
from typing import Optional

from app.schemas.unified import UnifiedRequest


class ProviderResult(dict):
    provider: str
    output: Optional[dict[str, Any]]
    error: Optional[str]
    latency_ms: int


class ProviderAdapter(ABC):
    provider: str

    @abstractmethod
    async def execute(self, req: UnifiedRequest, timeout_ms: int, trace_id: str) -> ProviderResult:
        raise NotImplementedError
