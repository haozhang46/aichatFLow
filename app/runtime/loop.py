from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from app.contracts.otie import ExecutionPlan, IntentEnvelope, PlanStep, RunResult
from app.observability.otie_trace_service import OtieTraceService
from app.orchestrator.graph import run_orchestrator
from app.policy.runtime_policy import RuntimePolicyService
from app.services.platform_trace_service import PlatformTraceService
from app.services.schema_validation import validate_against_schema, validate_llm_text_against_schema
from app.tools.registry import ToolRegistry


@dataclass
class WorkingMemory:
    step_outputs: dict[str, Any] = field(default_factory=dict)
    observations: list[str] = field(default_factory=list)
    replan_count: int = 0


class OtieRuntime:
    def __init__(
        self,
        tool_registry: ToolRegistry,
        policy_service: RuntimePolicyService,
        trace_service: OtieTraceService,
        platform_trace_service: PlatformTraceService,
    ) -> None:
        self._tool_registry = tool_registry
        self._policy_service = policy_service
        self._trace_service = trace_service
        self._platform_trace_service = platform_trace_service

    async def run(
        self,
        intent: IntentEnvelope,
        plan: ExecutionPlan,
        *,
        step_approvals: dict[str, bool] | None = None,
    ) -> RunResult:
        approvals = step_approvals or {}
        run_id = f"run_{uuid4().hex[:12]}"
        memory = WorkingMemory()
        self._platform_trace_service.emit(
            run_id,
            "run_started",
            run_id=run_id,
            span_id=self._platform_trace_service.new_span_id("run"),
            status="running",
            agentId=plan.mode,
            userId=str(intent.metadata.get("currentUserId") or "").strip(),
            metadata={"requestId": intent.request_id, "tenantId": intent.tenant_id},
        )

        self._trace_service.start_run(run_id, intent, plan)
        self._trace_service.append_event(run_id, "state_transition", fromState="pending", toState="running")
        allowed_tool_ids = [
            str(item).strip()
            for item in (intent.metadata.get("allowedToolIds") or [])
            if str(item).strip()
        ]

        for index, step in enumerate(plan.steps):
            if index >= plan.max_steps:
                return self._blocked_result(
                    run_id,
                    intent,
                    plan,
                    memory,
                    "failed",
                    "Execution stopped after reaching maxSteps.",
                )

            self._trace_service.append_event(
                run_id,
                "loop_tick",
                index=index,
                stepId=step.id,
                pendingSteps=len(plan.steps) - index,
            )
            self._trace_service.append_event(
                run_id,
                "observation_recorded",
                stepId=step.id,
                observation=self._build_observation(intent, step, memory),
            )
            self._trace_service.append_event(
                run_id,
                "step_started",
                stepId=step.id,
                kind=step.kind,
                action=step.action,
            )

            policy = self._policy_service.evaluate(step, approvals, allowed_tool_ids=allowed_tool_ids)
            self._trace_service.append_event(run_id, "policy_evaluated", stepId=step.id, **policy)
            if not policy.get("allow"):
                message = "Execution paused: user approval is required for this step."
                if policy.get("deniedTool"):
                    message = f"Execution blocked by policy: tool `{policy['deniedTool']}` is not allowed."
                self._trace_service.append_event(
                    run_id,
                    "state_transition",
                    fromState="running",
                    toState="awaiting_approval",
                    stepId=step.id,
                )
                return self._blocked_result(run_id, intent, plan, memory, "awaiting_approval", message)

            try:
                output = await self._execute_step(run_id, intent, plan, step, index, memory)
            except Exception as exc:
                max_replans = self._max_replans(intent)
                if memory.replan_count >= max_replans:
                    self._trace_service.append_event(
                        run_id,
                        "state_transition",
                        fromState="running",
                        toState="failed",
                        stepId=step.id,
                        reason="execution_error",
                    )
                    return self._blocked_result(
                        run_id,
                        intent,
                        plan,
                        memory,
                        "failed",
                        f"Execution failed at step {step.id}: {exc}",
                    )
                replanned = self._build_replanned_step(step, error=str(exc), memory=memory)
                plan.steps[index] = replanned
                memory.replan_count += 1
                self._trace_service.append_event(
                    run_id,
                    "replanned",
                    stepId=step.id,
                    newAction=replanned.action,
                    replanCount=memory.replan_count,
                    reason="execution_error",
                )
                self._trace_service.append_event(
                    run_id,
                    "state_transition",
                    fromState="running",
                    toState="replanning",
                    stepId=step.id,
                )
                self._trace_service.append_event(
                    run_id,
                    "state_transition",
                    fromState="replanning",
                    toState="running",
                    stepId=step.id,
                )
                output = await self._execute_step(run_id, intent, plan, replanned, index, memory)
            memory.step_outputs[step.id] = output
            memory.observations.append(f"{step.id}: {self._preview(output)}")
            self._trace_service.append_event(
                run_id,
                "step_completed",
                stepId=step.id,
                status="success",
                outputPreview=self._preview(output),
            )

        final_answer = self._stringify(memory.step_outputs.get(plan.steps[-1].id, "")) if plan.steps else ""
        self._trace_service.append_event(
            run_id,
            "state_transition",
            fromState="running",
            toState="completed",
        )
        self._trace_service.finish_run(
            run_id,
            status="completed",
            final_answer=final_answer,
            step_outputs=memory.step_outputs,
        )
        self._platform_trace_service.emit(
            run_id,
            "run_completed",
            run_id=run_id,
            span_id=self._platform_trace_service.new_span_id("run"),
            status="success",
            agentId=plan.mode,
            userId=str(intent.metadata.get("currentUserId") or "").strip(),
            metadata={"finalAnswerPreview": final_answer[:500]},
        )
        run = self._trace_service.get_run(run_id) or {}
        return RunResult(
            runId=run_id,
            status="completed",
            traceId=run_id,
            intent=intent,
            plan=plan,
            finalAnswer=final_answer,
            stepOutputs=memory.step_outputs,
            events=run.get("events", []),
        )

    async def _execute_step(
        self,
        run_id: str,
        intent: IntentEnvelope,
        plan: ExecutionPlan,
        step: PlanStep,
        index: int,
        memory: WorkingMemory,
    ) -> Any:
        if step.kind == "tool":
            if not step.tool_id:
                raise ValueError(f"step `{step.id}` is missing toolId")
            if step.tool_id == "retrieval":
                self._trace_service.append_event(
                    run_id,
                    "rag_search_started",
                    stepId=step.id,
                    tenantId=step.tool_args.get("tenantId"),
                    scope=step.tool_args.get("scope"),
                    topK=step.tool_args.get("topK"),
                    minScore=step.tool_args.get("minScore"),
                )
            if step.tool_id == "web-fetch":
                self._trace_service.append_event(
                    run_id,
                    "web_fetch_started",
                    stepId=step.id,
                    url=step.tool_args.get("url"),
                    maxChars=step.tool_args.get("maxChars"),
                )
            tool_context = {
                "currentUserId": str(intent.metadata.get("currentUserId") or "").strip(),
                "traceId": run_id,
                "parentSpanId": step.id,
                "traceSource": "otie_runtime",
                "currentAgentId": str(intent.metadata.get("agentId") or "").strip(),
                "allowedToolIds": intent.metadata.get("allowedToolIds"),
            }
            self._trace_service.append_event(
                run_id,
                "tool_call",
                stepId=step.id,
                toolId=step.tool_id,
                args=step.tool_args,
            )
            output = await self._tool_registry.execute(step.tool_id, step.tool_args, context=tool_context)
            if step.tool_id == "retrieval" and isinstance(output, dict):
                hits = output.get("hits") or []
                self._trace_service.append_event(
                    run_id,
                    "rag_search_completed",
                    stepId=step.id,
                    scope=output.get("scope"),
                    hitCount=len(hits) if isinstance(hits, list) else 0,
                )
                if isinstance(hits, list):
                    self._trace_service.append_event(
                        run_id,
                        "rag_hits_selected",
                        stepId=step.id,
                        hits=[
                            {
                                "documentId": item.get("documentId"),
                                "chunkId": item.get("chunkId"),
                                "score": item.get("score"),
                                "scope": item.get("scope"),
                            }
                            for item in hits[:5]
                            if isinstance(item, dict)
                        ],
                    )
            if step.tool_id == "web-fetch" and isinstance(output, dict):
                self._trace_service.append_event(
                    run_id,
                    "web_fetch_completed",
                    stepId=step.id,
                    url=output.get("url"),
                    finalUrl=output.get("finalUrl"),
                    statusCode=output.get("statusCode"),
                    title=output.get("title"),
                    contentLength=len(str(output.get("content") or "")),
                )
            return self._validate_step_output(run_id, intent, step, output)

        if step.kind == "reason":
            prompt = self._compose_reason_prompt(intent, step, index, len(plan.steps), memory)
            mode, answer, latency_ms = await run_orchestrator(
                prompt,
                strategy=step.agent,
                llm_config=intent.llm_config,
            )
            self._trace_service.append_event(
                run_id,
                "reasoning_result",
                stepId=step.id,
                mode=mode,
                latencyMs=latency_ms,
            )
            return self._validate_step_output(run_id, intent, step, answer)

        answer = self._compose_final_answer(intent, plan, memory)
        return self._validate_step_output(run_id, intent, step, answer)

    def _compose_reason_prompt(
        self,
        intent: IntentEnvelope,
        step: PlanStep,
        index: int,
        total_steps: int,
        memory: WorkingMemory,
    ) -> str:
        prompt = [
            f"User query: {intent.user_query}",
            f"Step {index + 1}/{total_steps}: {step.action}",
        ]
        if memory.observations:
            prompt.append("Prior observations:")
            prompt.extend(memory.observations[-5:])
        return "\n".join(prompt)

    def _compose_final_answer(
        self,
        intent: IntentEnvelope,
        plan: ExecutionPlan,
        memory: WorkingMemory,
    ) -> str:
        retrieval_outputs = [
            output
            for output in memory.step_outputs.values()
            if isinstance(output, dict) and isinstance(output.get("hits"), list)
        ]
        if retrieval_outputs:
            hits = []
            for output in retrieval_outputs:
                hits.extend(output.get("hits") or [])
            if not hits:
                scope_value = retrieval_outputs[0].get("scope")
                if scope_value:
                    return f"在当前知识范围 `{scope_value}` 下没有检索到与该问题相关的内容。"
                return "当前知识库中没有检索到与该问题相关的内容。"

            lines = [f"问题：{intent.user_query}", "", "根据知识库检索结果："]
            for idx, hit in enumerate(hits[:3]):
                title = str(hit.get("title") or f"片段 {idx + 1}")
                scope = str(hit.get("scope") or "")
                score = hit.get("score")
                content = str(hit.get("content") or "").strip()
                prefix = f"[{idx + 1}] {title}"
                if scope:
                    prefix += f" | scope={scope}"
                if isinstance(score, (int, float)):
                    prefix += f" | score={score:.4f}"
                lines.append(prefix)
                lines.append(content)
            return "\n".join(lines).strip()

        lines = [f"User request: {intent.user_query}", "", "Execution summary:"]
        for step in plan.steps:
            if step.id not in memory.step_outputs or step.kind == "respond":
                continue
            lines.append(f"- {step.id} {step.action}")
            lines.append(self._stringify(memory.step_outputs[step.id]))
        return "\n".join(lines).strip()

    def _build_observation(self, intent: IntentEnvelope, step: PlanStep, memory: WorkingMemory) -> str:
        return (
            f"query={intent.user_query[:120]}; "
            f"step={step.id}; "
            f"completed={len(memory.step_outputs)}"
        )

    def _validate_step_output(self, run_id: str, intent: IntentEnvelope, step: PlanStep, output: Any) -> Any:
        if step.output_schema is None:
            return output

        mode = self._schema_validation_mode(intent)
        if mode == "off":
            return output

        if isinstance(output, str):
            result = validate_llm_text_against_schema(output, step.output_schema)
        else:
            result = validate_against_schema(output, step.output_schema)

        self._trace_service.append_event(
            run_id,
            "schema_checked",
            stepId=step.id,
            ok=result.ok,
            error=result.error,
        )
        if result.ok:
            return result.parsed if result.parsed is not None else output
        if mode == "warn":
            return f"{self._stringify(output)}\n\n[schema warning] {result.error}"
        raise ValueError(f"schema validation failed: {result.error or 'unknown error'}")

    def _schema_validation_mode(self, intent: IntentEnvelope) -> str:
        raw = intent.constraints.get("requestInputs", {}).get("schemaValidationMode")
        if isinstance(raw, str) and raw.lower() in {"off", "warn", "block"}:
            return raw.lower()
        return "warn"

    def _max_replans(self, intent: IntentEnvelope) -> int:
        raw = intent.constraints.get("requestInputs", {}).get("maxReplans")
        if isinstance(raw, int) and raw >= 0:
            return raw
        return 1

    def _build_replanned_step(self, step: PlanStep, *, error: str, memory: WorkingMemory) -> PlanStep:
        if step.kind == "tool":
            return step.model_copy(
                update={
                    "kind": "reason",
                    "tool_id": None,
                    "tool_args": {},
                    "action": f"{step.action} Fallback to direct reasoning because the tool failed: {error}",
                }
            )
        if step.output_schema:
            return step.model_copy(
                update={
                    "action": (
                        f"{step.action}\n"
                        f"Return output that satisfies the required JSON schema. "
                        f"Previous validation error: {error}"
                    )
                }
            )
        return step.model_copy(update={"action": f"{step.action}\nAdjust approach after error: {error}"})

    def _blocked_result(
        self,
        run_id: str,
        intent: IntentEnvelope,
        plan: ExecutionPlan,
        memory: WorkingMemory,
        status: str,
        message: str,
    ) -> RunResult:
        self._platform_trace_service.emit(
            run_id,
            "run_completed",
            run_id=run_id,
            span_id=self._platform_trace_service.new_span_id("run"),
            status="failed" if status == "failed" else "awaiting_approval",
            agentId=plan.mode,
            userId=str(intent.metadata.get("currentUserId") or "").strip(),
            metadata={"finalAnswerPreview": message[:500]},
        )
        self._trace_service.finish_run(
            run_id,
            status=status,
            final_answer=message,
            step_outputs=memory.step_outputs,
        )
        run = self._trace_service.get_run(run_id) or {}
        return RunResult(
            runId=run_id,
            status=status,
            traceId=run_id,
            intent=intent,
            plan=plan,
            finalAnswer=message,
            stepOutputs=memory.step_outputs,
            events=run.get("events", []),
        )

    def _preview(self, value: Any) -> str:
        return self._stringify(value)[:300]

    def _stringify(self, value: Any) -> str:
        if isinstance(value, str):
            return value
        return str(value)
