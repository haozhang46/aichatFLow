from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from time import monotonic
from typing import Any

from app.orchestrator.graph import run_orchestrator
from app.runtime.platform_file_adapter import PlatformFileAdapter
from app.runtime.platform_tool_adapter import PlatformToolAdapter
from app.runtime.platform_trace_adapter import PlatformTraceAdapter


@dataclass
class DeepAgentInvokeRequest:
    input: dict[str, Any]
    context: dict[str, Any]
    runtime_options: dict[str, Any]
    llm_config: dict[str, str] | None


@dataclass
class DeepAgentInvokeContext:
    trace_id: str
    run_id: str
    user_id: str
    agent_id: str
    tenant_id: str | None
    allowed_tool_ids: list[str]


@dataclass
class DeepAgentInvokeResult:
    status: str
    mode: str
    answer: str
    events: list[dict[str, Any]]
    step_outputs: dict[str, Any]
    latency_ms: int
    error: dict[str, Any] | None = None


class DeepAgentRuntimeAdapter:
    def __init__(
        self,
        tool_adapter: PlatformToolAdapter,
        file_adapter: PlatformFileAdapter,
        trace_adapter: PlatformTraceAdapter,
    ) -> None:
        self._tool_adapter = tool_adapter
        self._file_adapter = file_adapter
        self._trace_adapter = trace_adapter

    async def invoke(
        self,
        agent_spec: dict[str, Any],
        request: DeepAgentInvokeRequest,
        context: DeepAgentInvokeContext,
    ) -> DeepAgentInvokeResult:
        agent_name = str(agent_spec.get("name") or agent_spec.get("label") or context.agent_id)
        system_prompt = str(agent_spec.get("systemPrompt") or "").strip()
        runtime = agent_spec.get("runtime") if isinstance(agent_spec.get("runtime"), dict) else {}
        memory = agent_spec.get("memory") if isinstance(agent_spec.get("memory"), dict) else {}
        policy = agent_spec.get("policy") if isinstance(agent_spec.get("policy"), dict) else {}
        strategy = str(runtime.get("mode") or "agent").strip()
        if strategy not in {"agent", "react", "workflow"}:
            strategy = "agent"

        started = monotonic()
        step_outputs: dict[str, Any] = {}
        events: list[dict[str, Any]] = []
        self._trace_adapter.emit_run_started(
            trace_id=context.trace_id,
            run_id=context.run_id,
            agent_id=context.agent_id,
            user_id=context.user_id,
            metadata={
                "runtimeEngine": "deepagent",
                "allowedTools": context.allowed_tool_ids,
                "input": request.input,
                "context": request.context,
            },
        )
        memory_context = await self._hydrate_memory(agent_spec, request, context, memory=memory, policy=policy)
        if memory_context:
            step_outputs["memory"] = memory_context
            events.append({"type": "prefetch_memory", "workspace": memory_context.get("workspace")})
        rag_context = await self._prefetch_retrieval(request, context)
        if rag_context:
            step_outputs["retrieval"] = rag_context
            events.append({"type": "prefetch_retrieval", "hitCount": len(rag_context.get("hits") or []) if isinstance(rag_context, dict) else 0})
        prompt = self._compose_prompt(
            agent_name,
            system_prompt,
            request,
            context,
            memory_context=memory_context,
            rag_context=rag_context,
        )
        self._trace_adapter.emit_step_started(
            trace_id=context.trace_id,
            run_id=context.run_id,
            step_id="deepagent_main",
            agent_id=context.agent_id,
            metadata={"action": "deepagent_reason_and_respond", "strategy": strategy},
        )
        try:
            mode, answer, _ = await run_orchestrator(prompt, strategy=strategy, llm_config=request.llm_config)
        except Exception as exc:
            self._trace_adapter.emit_run_completed(
                trace_id=context.trace_id,
                run_id=context.run_id,
                agent_id=context.agent_id,
                user_id=context.user_id,
                status="failed",
                metadata={"runtimeEngine": "deepagent", "error": {"message": str(exc)}},
            )
            return DeepAgentInvokeResult(
                status="failed",
                mode=strategy,
                answer="",
                events=events,
                step_outputs=step_outputs,
                latency_ms=int((monotonic() - started) * 1000),
                error={"code": "agent_invoke_failed", "message": str(exc)},
            )

        writeback = await self._writeback_story_workspace(
            request,
            context,
            policy=policy,
            answer=answer,
        )
        if writeback:
            step_outputs["writeback"] = writeback
            events.append({"type": "writeback", "path": writeback.get("path"), "mode": writeback.get("mode")})

        self._trace_adapter.emit_step_completed(
            trace_id=context.trace_id,
            run_id=context.run_id,
            step_id="deepagent_main",
            agent_id=context.agent_id,
            metadata={"mode": mode, "outputPreview": answer[:500]},
        )
        self._trace_adapter.emit_run_completed(
            trace_id=context.trace_id,
            run_id=context.run_id,
            agent_id=context.agent_id,
            user_id=context.user_id,
            status="success",
            metadata={"runtimeEngine": "deepagent", "mode": mode, "finalAnswerPreview": answer[:500]},
        )
        return DeepAgentInvokeResult(
            status="success",
            mode=mode,
            answer=answer,
            events=events,
            step_outputs=step_outputs,
            latency_ms=int((monotonic() - started) * 1000),
            error=None,
        )

    def _compose_prompt(
        self,
        agent_name: str,
        system_prompt: str,
        request: DeepAgentInvokeRequest,
        context: DeepAgentInvokeContext,
        *,
        memory_context: dict[str, Any] | None,
        rag_context: dict[str, Any] | None,
    ) -> str:
        allowed_tools = self._tool_adapter.list_allowed_tools(context.allowed_tool_ids)
        tool_names = ", ".join(str(item.get("id") or "") for item in allowed_tools if str(item.get("id") or "").strip())
        user_message = str(request.input.get("message") or request.input.get("prompt") or "").strip()
        prompt = (
            f"You are `{agent_name}` running via the DeepAgent adapter.\n"
            + (f"System instructions:\n{system_prompt}\n\n" if system_prompt else "")
            + (f"Allowed tools: {tool_names}\n" if tool_names else "")
            + (f"Workspace context: {request.context}\n" if request.context else "")
        )
        if memory_context:
            prompt += f"Loaded workspace memory:\n{memory_context}\n\n"
        if rag_context:
            prompt += f"Retrieved knowledge:\n{rag_context}\n\n"
        prompt += f"User request:\n{user_message}"
        return prompt

    async def _hydrate_memory(
        self,
        agent_spec: dict[str, Any],
        request: DeepAgentInvokeRequest,
        context: DeepAgentInvokeContext,
        *,
        memory: dict[str, Any],
        policy: dict[str, Any],
    ) -> dict[str, Any] | None:
        if str(memory.get("type") or "none").strip().lower() != "file":
            return None
        if not bool(policy.get("allowFileAccess")):
            return None
        workspace = str(request.context.get("workspace") or "").strip().strip("/")
        if not workspace:
            return None
        if "file-read" not in context.allowed_tool_ids:
            return None
        window_size = int(memory.get("windowSize") or 4)
        step_id = "deepagent_memory"
        self._trace_adapter.emit_step_started(
            trace_id=context.trace_id,
            run_id=context.run_id,
            step_id=step_id,
            agent_id=context.agent_id,
            metadata={"action": "hydrate_workspace_memory", "workspace": workspace},
        )
        files_to_read = [
            f"{workspace}/story.json",
            f"{workspace}/overview.md",
            f"{workspace}/setting.md",
            f"{workspace}/characters.md",
            f"{workspace}/outline.md",
            f"{workspace}/notes.md",
        ]
        hydrated: dict[str, Any] = {"workspace": workspace, "files": {}}
        for path in files_to_read:
            item = await self._safe_file_read(path, context)
            if item is not None:
                hydrated["files"][path] = item
        if "file-list" in context.allowed_tool_ids:
            chapter_tree = await self._safe_tool_execute(
                "file-list",
                {"path": f"{workspace}/chapters"},
                context=context,
                parent_span_id=step_id,
            )
            if isinstance(chapter_tree, dict):
                items = chapter_tree.get("items") if isinstance(chapter_tree.get("items"), list) else []
                chapter_paths = [
                    str(item.get("path") or "").removeprefix("stories/")
                    for item in items
                    if isinstance(item, dict) and str(item.get("type") or "") == "file"
                ]
                chapter_paths = sorted([p for p in chapter_paths if p])[-window_size:]
                chapters: dict[str, Any] = {}
                for chapter_path in chapter_paths:
                    item = await self._safe_file_read(chapter_path, context)
                    if item is not None:
                        chapters[chapter_path] = item
                if chapters:
                    hydrated["chapters"] = chapters
        self._trace_adapter.emit_step_completed(
            trace_id=context.trace_id,
            run_id=context.run_id,
            step_id=step_id,
            agent_id=context.agent_id,
            metadata={"workspace": workspace, "loadedFiles": len(hydrated.get("files") or {})},
        )
        return hydrated

    async def _prefetch_retrieval(
        self,
        request: DeepAgentInvokeRequest,
        context: DeepAgentInvokeContext,
    ) -> dict[str, Any] | None:
        if "retrieval" not in context.allowed_tool_ids:
            return None
        raw_rag = request.context.get("rag") if isinstance(request.context.get("rag"), dict) else {}
        enabled = bool(raw_rag.get("enabled"))
        tenant_id = str(raw_rag.get("tenantId") or context.tenant_id or "").strip()
        query = str(raw_rag.get("query") or request.input.get("message") or "").strip()
        if not enabled or not tenant_id or not query:
            return None
        step_id = "deepagent_retrieval"
        self._trace_adapter.emit_step_started(
            trace_id=context.trace_id,
            run_id=context.run_id,
            step_id=step_id,
            agent_id=context.agent_id,
            metadata={"action": "prefetch_retrieval", "tenantId": tenant_id},
        )
        result = await self._safe_tool_execute(
            "retrieval",
            {
                "tenantId": tenant_id,
                "query": query,
                **({k: raw_rag[k] for k in ("scope", "topK", "minScore") if raw_rag.get(k) is not None}),
            },
            context=context,
            parent_span_id=step_id,
        )
        if result is None:
            return None
        self._trace_adapter.emit_step_completed(
            trace_id=context.trace_id,
            run_id=context.run_id,
            step_id=step_id,
            agent_id=context.agent_id,
            metadata={"hitCount": len(result.get("hits") or []) if isinstance(result, dict) else 0},
        )
        return result

    async def _safe_file_read(self, path: str, context: DeepAgentInvokeContext) -> dict[str, Any] | None:
        try:
            return await self._file_adapter.read(
                path,
                user_id=context.user_id,
                agent_id=context.agent_id,
                allowed_tool_ids=context.allowed_tool_ids,
                trace_id=context.trace_id,
            )
        except Exception:
            return None

    async def _safe_file_write(
        self,
        path: str,
        content: str,
        context: DeepAgentInvokeContext,
    ) -> dict[str, Any] | None:
        try:
            return await self._file_adapter.write(
                path,
                content,
                user_id=context.user_id,
                agent_id=context.agent_id,
                allowed_tool_ids=context.allowed_tool_ids,
                trace_id=context.trace_id,
            )
        except Exception:
            return None

    async def _safe_tool_execute(
        self,
        tool_id: str,
        args: dict[str, Any],
        *,
        context: DeepAgentInvokeContext,
        parent_span_id: str | None,
    ) -> dict[str, Any] | None:
        try:
            return await self._tool_adapter.execute(
                tool_id,
                args,
                user_id=context.user_id,
                agent_id=context.agent_id,
                allowed_tool_ids=context.allowed_tool_ids,
                trace_id=context.trace_id,
                parent_span_id=parent_span_id,
            )
        except Exception:
            return None

    async def _writeback_story_workspace(
        self,
        request: DeepAgentInvokeRequest,
        context: DeepAgentInvokeContext,
        *,
        policy: dict[str, Any],
        answer: str,
    ) -> dict[str, Any] | None:
        if not bool(policy.get("allowFileAccess")):
            return None
        workspace = str(request.context.get("workspace") or "").strip().strip("/")
        if not workspace:
            return None
        if "file-patch" not in context.allowed_tool_ids and "file-write" not in context.allowed_tool_ids:
            return None
        step_id = "deepagent_writeback"
        user_message = str(request.input.get("message") or request.input.get("prompt") or "").lower()
        target = f"{workspace}/outline.md" if "outline" in user_message or "提纲" in user_message else f"{workspace}/notes.md"
        story_json_path = f"{workspace}/story.json"
        if "file-mkdir" in context.allowed_tool_ids:
            await self._safe_tool_execute(
                "file-mkdir",
                {"path": workspace},
                context=context,
                parent_span_id=step_id,
            )

        story_state_saved = False
        story_state_path: str | None = None
        if "file-write" in context.allowed_tool_ids and "file-read" in context.allowed_tool_ids:
            existing_story = await self._safe_file_read(story_json_path, context)
            next_story_state = self._build_story_state(
                request=request,
                context=context,
                answer=answer,
                story_path=target,
                existing_story=existing_story,
            )
            story_write = await self._safe_file_write(
                story_json_path,
                json.dumps(next_story_state, ensure_ascii=False, indent=2),
                context,
            )
            if isinstance(story_write, dict):
                story_state_saved = True
                story_state_path = str(story_write.get("path") or story_json_path)

        content = f"\n\n## DeepAgent Update\n\n{answer.strip()}\n"
        if "file-patch" in context.allowed_tool_ids:
            result = await self._safe_tool_execute(
                "file-patch",
                {"path": target, "content": content, "mode": "append"},
                context=context,
                parent_span_id=step_id,
            )
            if isinstance(result, dict):
                result["storyStateSaved"] = story_state_saved
                if story_state_path:
                    result["storyStatePath"] = story_state_path
                return result
        if "file-write" in context.allowed_tool_ids:
            existing = await self._safe_file_read(target, context)
            merged = f"{str((existing or {}).get('content') or '')}{content}"
            result = await self._safe_file_write(
                target,
                merged,
                context,
            )
            if isinstance(result, dict):
                result["mode"] = "replace"
                result["storyStateSaved"] = story_state_saved
                if story_state_path:
                    result["storyStatePath"] = story_state_path
                return result
        return None

    def _build_story_state(
        self,
        *,
        request: DeepAgentInvokeRequest,
        context: DeepAgentInvokeContext,
        answer: str,
        story_path: str,
        existing_story: dict[str, Any] | None,
    ) -> dict[str, Any]:
        raw_content = str((existing_story or {}).get("content") or "").strip()
        story_state: dict[str, Any] = {}
        if raw_content:
            try:
                parsed = json.loads(raw_content)
                if isinstance(parsed, dict):
                    story_state = parsed
            except json.JSONDecodeError:
                story_state = {}

        now = datetime.now(timezone.utc).isoformat()
        workspace = str(request.context.get("workspace") or "").strip().strip("/")
        input_message = str(request.input.get("message") or request.input.get("prompt") or "").strip()
        story_state.setdefault("storyId", workspace or context.agent_id)
        story_state.setdefault("title", workspace or context.agent_id)
        story_state["workspace"] = workspace
        story_state["status"] = "drafting"
        story_state["updatedAt"] = now
        story_state["lastAgentRun"] = {
            "agentId": context.agent_id,
            "runId": context.run_id,
            "traceId": context.trace_id,
            "userId": context.user_id,
            "input": input_message,
            "writebackPath": story_path,
            "answerPreview": answer[:500],
            "updatedAt": now,
        }
        return story_state
