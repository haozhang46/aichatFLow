from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


class ChatMessage(BaseModel):
    role: str = "user"
    content: str


class OtieRequestInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    request_id: str = Field(default_factory=lambda: _new_id("req"), alias="requestId")
    tenant_id: str = Field(default="default", alias="tenantId")
    request_type: Literal["chat", "workflow"] = Field(default="chat", alias="requestType")
    messages: list[ChatMessage] = Field(default_factory=list)
    inputs: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_request(self) -> "OtieRequestInput":
        if self.request_type == "chat" and not self.messages:
            raise ValueError("messages are required for chat")
        return self


class IntentEnvelope(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    intent_id: str = Field(default_factory=lambda: _new_id("intent"), alias="intentId")
    request_id: str = Field(alias="requestId")
    tenant_id: str = Field(alias="tenantId")
    source_request_type: str = Field(alias="sourceRequestType")
    user_query: str = Field(alias="userQuery")
    mode_hint: Literal["auto", "agent", "react", "workflow"] = Field(default="auto", alias="modeHint")
    execution_mode: Literal["auto_exec", "user_exec"] = Field(default="auto_exec", alias="executionMode")
    llm_config: Optional[dict[str, str]] = Field(default=None, alias="llmConfig")
    metadata: dict[str, Any] = Field(default_factory=dict)
    constraints: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat(), alias="createdAt")


class RetryPolicy(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    max_retries: int = Field(default=0, alias="maxRetries")
    backoff_ms: int = Field(default=0, alias="backoffMs")


class PlanStep(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(alias="stepId")
    kind: Literal["reason", "tool", "respond"]
    action: str
    depends_on: list[str] = Field(default_factory=list, alias="dependsOn")
    agent: Literal["auto", "agent", "react", "workflow"] = "auto"
    tool_id: Optional[str] = Field(default=None, alias="toolId")
    tool_args: dict[str, Any] = Field(default_factory=dict, alias="toolArgs")
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy, alias="retryPolicy")
    timeout_ms: Optional[int] = Field(default=None, alias="timeoutMs")
    output_schema: Optional[dict[str, Any]] = Field(default=None, alias="outputSchema")


class ExecutionPlan(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    plan_id: str = Field(default_factory=lambda: _new_id("plan"), alias="planId")
    intent_id: str = Field(alias="intentId")
    mode: Literal["agent", "react", "workflow"] = "agent"
    status: Literal["draft", "ready", "running", "completed", "failed", "blocked"] = "ready"
    max_steps: int = Field(default=8, alias="maxSteps")
    steps: list[PlanStep] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat(), alias="createdAt")


class OtiePlanRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    request: Optional[OtieRequestInput] = None
    intent: Optional[IntentEnvelope] = None

    @model_validator(mode="after")
    def validate_payload(self) -> "OtiePlanRequest":
        if self.request is None and self.intent is None:
            raise ValueError("either request or intent is required")
        return self


class OtieRunRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    request: Optional[OtieRequestInput] = None
    intent: Optional[IntentEnvelope] = None
    plan: Optional[ExecutionPlan] = None
    step_approvals: dict[str, bool] = Field(default_factory=dict, alias="stepApprovals")

    @model_validator(mode="after")
    def validate_payload(self) -> "OtieRunRequest":
        if self.request is None and self.intent is None:
            raise ValueError("either request or intent is required")
        return self


class RunResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    run_id: str = Field(alias="runId")
    status: str
    trace_id: str = Field(alias="traceId")
    intent: IntentEnvelope
    plan: ExecutionPlan
    final_answer: str = Field(alias="finalAnswer")
    step_outputs: dict[str, Any] = Field(default_factory=dict, alias="stepOutputs")
    events: list[dict[str, Any]] = Field(default_factory=list)
