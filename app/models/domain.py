from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional, Union


RequestType = Literal["chat", "workflow"]
Provider = Literal["fastgpt", "dify"]
Status = Literal["success", "partial", "failed"]


@dataclass
class IntegrationRoute:
    id: str
    tenant_id: str
    request_type: RequestType
    primary_provider: Provider
    fallback_provider: Union[Provider, Literal["none"]]
    timeout_ms: int = 8000
    enabled: bool = True
    match_tags: list[str] = field(default_factory=list)


@dataclass
class TraceEvent:
    at: str
    provider: Provider
    action: str
    result: Literal["ok", "error"]
    detail: Optional[str] = None


@dataclass
class ExecutionTrace:
    trace_id: str
    request_id: str
    route_id: str
    events: list[TraceEvent] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
