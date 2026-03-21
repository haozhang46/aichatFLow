from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator


class UnifiedRequest(BaseModel):
    request_id: str = Field(alias="requestId")
    tenant_id: str = Field(alias="tenantId")
    request_type: Literal["chat", "workflow"] = Field(alias="requestType")
    messages: Optional[list[dict[str, Any]]] = None
    workflow_id: Optional[str] = Field(default=None, alias="workflowId")
    inputs: Optional[dict[str, Any]] = None
    metadata: Optional[dict[str, Any]] = None

    @model_validator(mode="after")
    def validate_mode(self):
        if self.request_type == "chat" and (not self.messages):
            raise ValueError("messages are required for chat")
        if self.request_type == "workflow" and not self.workflow_id:
            raise ValueError("workflowId is required for workflow")
        return self


class UnifiedResponse(BaseModel):
    request_id: str = Field(alias="requestId")
    provider: Literal["fastgpt", "dify", "langchain"]
    status: Literal["success", "partial", "failed"]
    output: Optional[dict[str, Any]] = None
    error: Optional[dict[str, Any]] = None
    latency_ms: int = Field(alias="latencyMs")
    trace_id: str = Field(alias="traceId")
    fallback_used: bool = Field(alias="fallbackUsed")
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class IntegrationRouteIn(BaseModel):
    id: str
    tenant_id: str = Field(alias="tenantId")
    request_type: Literal["chat", "workflow"] = Field(alias="requestType")
    primary_provider: Literal["fastgpt", "dify"] = Field(alias="primaryProvider")
    fallback_provider: Literal["fastgpt", "dify", "none"] = Field(alias="fallbackProvider")
    timeout_ms: int = Field(default=8000, alias="timeoutMs")
    enabled: bool = True
    match_tags: list[str] = Field(default_factory=list, alias="matchTags")
