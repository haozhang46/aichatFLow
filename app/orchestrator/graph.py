from __future__ import annotations

import json
import os
import time
from typing import Any, AsyncGenerator, Dict, Literal, Optional, TypedDict, Union

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, StateGraph

from app.core.config import settings

Mode = Literal["agent", "react", "workflow"]
Strategy = Literal["auto", "agent", "react", "workflow"]


class GraphState(TypedDict):
    query: str
    strategy: Strategy
    mode: Mode
    answer: str


def _offline_mode(llm_config: Optional[Dict[str, str]] = None) -> bool:
    # In tests you typically don't have OPENAI_API_KEY, so fall back to deterministic mode selection.
    if os.environ.get("NODE_ENV") == "test":
        return True
    if llm_config and llm_config.get("apiKey"):
        return False
    return not settings.openai_api_key


def _heuristic_router(query: str) -> Mode:
    q = query.lower()
    if any(k in q for k in ["workflow", "流程", "步骤", "plan", "方案"]):
        return "workflow"
    if any(k in q for k in ["react", "反思", "行动", "观察", "thought"]):
        return "react"
    return "agent"


def _select_mode(query: str, strategy: Strategy) -> Mode:
    if strategy != "auto":
        return strategy  # type: ignore[return-value]
    return _heuristic_router(query)


def build_orchestrator_graph(llm_config: Optional[Dict[str, str]] = None):
    if _offline_mode(llm_config):
        # In offline/test mode, use heuristic routing and templated outputs (no network calls).
        def router(state: GraphState) -> GraphState:
            if state["strategy"] != "auto":
                state["mode"] = state["strategy"]
            else:
                state["mode"] = _heuristic_router(state["query"])
            return state

        def agent_node(state: GraphState) -> GraphState:
            state["answer"] = f"[agent] {state['query']}"
            return state

        def react_node(state: GraphState) -> GraphState:
            state["answer"] = f"[react] Thought: ... Action: none Observation: ... Final: {state['query']}"
            return state

        def workflow_node(state: GraphState) -> GraphState:
            state["answer"] = f"[workflow] 1) 解析需求 2) 拟定步骤 3) 输出答案：{state['query']}"
            return state

    else:
        api_key = (llm_config or {}).get("apiKey") or settings.openai_api_key
        base_url = (llm_config or {}).get("baseUrl") or settings.openai_base_url
        model = (llm_config or {}).get("model") or settings.openai_model
        llm = ChatOpenAI(
            api_key=api_key,
            base_url=base_url,
            model=model,
            temperature=0.2,
        )

        router_prompt = ChatPromptTemplate.from_messages(
            [
                SystemMessage(
                    content=(
                        "You are a router. Choose the best execution mode for the user query.\n"
                        "Return ONLY valid JSON with schema: {\"mode\": \"agent\"|\"react\"|\"workflow\"}."
                    )
                ),
                ("human", "Query: {query}"),
            ]
        )

        async def router(state: GraphState) -> GraphState:  # type: ignore[override]
            if state["strategy"] != "auto":
                state["mode"] = state["strategy"]  # type: ignore[assignment]
                return state

            resp = router_prompt.format_messages(query=state["query"])
            raw = await llm.ainvoke(resp)
            content = getattr(raw, "content", "") or ""
            try:
                data = json.loads(content)
                state["mode"] = data["mode"]
            except Exception:
                # Fallback to heuristic if parsing fails
                state["mode"] = _heuristic_router(state["query"])
            return state

        agent_prompt = ChatPromptTemplate.from_messages(
            [
                SystemMessage(content="You are an AI agent. Answer the user directly and helpfully."),
                ("human", "{query}"),
            ]
        )

        async def agent_node(state: GraphState) -> GraphState:  # type: ignore[override]
            resp = agent_prompt.format_messages(query=state["query"])
            raw = await llm.ainvoke(resp)
            state["answer"] = getattr(raw, "content", "") or ""
            return state

        react_prompt = ChatPromptTemplate.from_messages(
            [
                SystemMessage(
                    content=(
                        "You are a ReAct-style reasoning assistant.\n"
                        "Return in this format:\n"
                        "Thought: ...\nAction: none\nObservation: ...\nFinal: ...\n"
                    )
                ),
                ("human", "{query}"),
            ]
        )

        async def react_node(state: GraphState) -> GraphState:  # type: ignore[override]
            resp = react_prompt.format_messages(query=state["query"])
            raw = await llm.ainvoke(resp)
            state["answer"] = getattr(raw, "content", "") or ""
            return state

        workflow_prompt = ChatPromptTemplate.from_messages(
            [
                SystemMessage(
                    content=(
                        "You are a workflow executor.\n"
                        "First output: Plan (3 bullets).\n"
                        "Then output: Answer."
                    )
                ),
                ("human", "{query}"),
            ]
        )

        async def workflow_node(state: GraphState) -> GraphState:  # type: ignore[override]
            resp = workflow_prompt.format_messages(query=state["query"])
            raw = await llm.ainvoke(resp)
            state["answer"] = getattr(raw, "content", "") or ""
            return state

    graph = StateGraph(GraphState)
    graph.add_node("router", router)
    graph.add_node("agent", agent_node)
    graph.add_node("react", react_node)
    graph.add_node("workflow", workflow_node)
    graph.set_entry_point("router")
    graph.add_conditional_edges(
        "router",
        lambda s: s["mode"],
        {"agent": "agent", "react": "react", "workflow": "workflow"},
    )
    graph.add_edge("agent", END)
    graph.add_edge("react", END)
    graph.add_edge("workflow", END)

    return graph.compile()


async def run_orchestrator(
    query: str, strategy: Strategy = "auto", llm_config: Optional[Dict[str, str]] = None
) -> tuple[Mode, str, int]:
    start = time.monotonic()
    try:
        orchestrator = build_orchestrator_graph(llm_config=llm_config)
        state: GraphState = {"query": query, "strategy": strategy, "mode": "agent", "answer": ""}
        out = await orchestrator.ainvoke(state)
    except Exception:
        # Gracefully fallback to heuristic mode when provider credentials/network fail.
        mode = _select_mode(query, strategy)
        out = {
            "mode": mode,
            "answer": f"[fallback:{mode}] LLM temporarily unavailable, switched to heuristic response. Query: {query}",
        }
    latency_ms = int((time.monotonic() - start) * 1000)
    return out["mode"], out["answer"], latency_ms


def _build_plan_lines(query: str, mode: Mode) -> list[str]:
    if mode == "workflow":
        return [
            "澄清用户目标与上下文（地点、时间范围、输出粒度）。",
            "按工作流拆解执行步骤，并逐步产出关键中间结果。",
            "汇总最终答案，并附上关键链路说明。",
        ]
    if mode == "react":
        return [
            "Thought: 先判断问题意图与缺失信息。",
            "Action: 选择合适步骤推进（如补充询问/检索/推理）。",
            "Observation -> Final: 根据观察结果汇总最终回答。",
        ]
    return [
        "理解用户问题意图并提取核心约束。",
        "使用 agent 直接求解并生成可读答案。",
        "补充必要说明，确保结果可执行。",
    ]


def _extract_json_object(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:].strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return json.loads(text[start : end + 1])
    raise ValueError("invalid json")


async def _build_plan_lines_with_llm(
    query: str, mode: Mode, llm_config: Optional[Dict[str, str]] = None
) -> list[str]:
    api_key = (llm_config or {}).get("apiKey") or settings.openai_api_key
    base_url = (llm_config or {}).get("baseUrl") or settings.openai_base_url
    model = (llm_config or {}).get("model") or settings.openai_model
    llm = ChatOpenAI(
        api_key=api_key,
        base_url=base_url,
        model=model,
        temperature=0.2,
    )
    plan_prompt = ChatPromptTemplate.from_messages(
        [
            SystemMessage(
                content=(
                    "You are a planning assistant.\n"
                    "Generate a concise executable plan for the query.\n"
                    "Return ONLY JSON with schema:\n"
                    "{\"plan\": [\"step1\", \"step2\", \"step3\"]}\n"
                    "Rules:\n"
                    "- 3 to 5 steps\n"
                    "- each step must be concrete and actionable\n"
                    "- no markdown, no explanations"
                )
            ),
            ("human", "mode={mode}\nquery={query}"),
        ]
    )
    resp = plan_prompt.format_messages(query=query, mode=mode)
    raw = await llm.ainvoke(resp)
    content = str(getattr(raw, "content", "") or "").strip()
    data = _extract_json_object(content)
    plan = data.get("plan")
    if not isinstance(plan, list):
        raise ValueError("plan must be list")
    lines = [str(x).strip() for x in plan if str(x).strip()]
    if len(lines) < 2:
        raise ValueError("plan too short")
    return lines[:5]


async def build_plan(
    query: str, strategy: Strategy = "auto", llm_config: Optional[Dict[str, str]] = None
) -> tuple[Mode, list[str], int]:
    start = time.monotonic()
    if strategy == "auto" and not _offline_mode(llm_config):
        mode, _, _ = await run_orchestrator(query, strategy=strategy, llm_config=llm_config)
    else:
        mode = _select_mode(query, strategy)
    latency_ms = int((time.monotonic() - start) * 1000)
    if not _offline_mode(llm_config):
        try:
            plan_lines = await _build_plan_lines_with_llm(query, mode, llm_config=llm_config)
            return mode, plan_lines, latency_ms
        except Exception:
            # Fallback to deterministic template plan when LLM planning fails.
            pass
    return mode, _build_plan_lines(query, mode), latency_ms


def _heuristic_evidence(query: str) -> list[dict[str, str]]:
    q = query.lower()
    if any(k in q for k in ["学习", "学习计划", "learn", "roadmap", "前端", "backend", "python", "java"]):
        return [
            {"title": "MDN Web Docs", "url": "https://developer.mozilla.org/"},
            {"title": "freeCodeCamp", "url": "https://www.freecodecamp.org/"},
            {"title": "roadmap.sh", "url": "https://roadmap.sh/"},
        ]
    return [
        {"title": "Wikipedia", "url": "https://www.wikipedia.org/"},
        {"title": "Stack Overflow", "url": "https://stackoverflow.com/"},
    ]


async def build_plan_context(
    query: str, strategy: Strategy = "auto", llm_config: Optional[Dict[str, str]] = None
) -> dict[str, Any]:
    mode, plan_lines, latency_ms = await build_plan(query, strategy=strategy, llm_config=llm_config)
    base_context = {
        "mode": mode,
        "plan": plan_lines,
        "latencyMs": latency_ms,
        "intentDescription": f"用户希望解决：{query}",
        "thinking": "先明确用户目标与约束，再检索公开资料，最后汇总为可执行计划。",
        "searchEvidence": _heuristic_evidence(query),
    }
    if _offline_mode(llm_config):
        return base_context

    try:
        api_key = (llm_config or {}).get("apiKey") or settings.openai_api_key
        base_url = (llm_config or {}).get("baseUrl") or settings.openai_base_url
        model = (llm_config or {}).get("model") or settings.openai_model
        llm = ChatOpenAI(
            api_key=api_key,
            base_url=base_url,
            model=model,
            temperature=0.2,
        )
        context_prompt = ChatPromptTemplate.from_messages(
            [
                SystemMessage(
                    content=(
                        "You are a planning assistant.\n"
                        "Return ONLY JSON:\n"
                        "{"
                        "\"intentDescription\": \"...\","
                        "\"thinking\": \"...\","
                        "\"searchEvidence\": [{\"title\":\"...\",\"url\":\"https://...\"}]"
                        "}\n"
                        "Rules:\n"
                        "- intentDescription must be one short sentence in Chinese.\n"
                        "- thinking must summarize why and how to search before planning.\n"
                        "- searchEvidence should contain 2-5 useful public web resources.\n"
                        "- URLs must start with https://"
                    )
                ),
                ("human", "query={query}\nmode={mode}\nplan={plan}"),
            ]
        )
        resp = context_prompt.format_messages(query=query, mode=mode, plan="\n".join(plan_lines))
        raw = await llm.ainvoke(resp)
        data = _extract_json_object(str(getattr(raw, "content", "") or ""))
        intent = str(data.get("intentDescription", "")).strip() or base_context["intentDescription"]
        thinking = str(data.get("thinking", "")).strip() or base_context["thinking"]
        evidence_raw = data.get("searchEvidence")
        evidence: list[dict[str, str]] = []
        if isinstance(evidence_raw, list):
            for item in evidence_raw:
                if not isinstance(item, dict):
                    continue
                title = str(item.get("title", "")).strip()
                url = str(item.get("url", "")).strip()
                if not title or not url.startswith("https://"):
                    continue
                evidence.append({"title": title, "url": url})
        if not evidence:
            evidence = base_context["searchEvidence"]
        return {
            **base_context,
            "intentDescription": intent,
            "thinking": thinking,
            "searchEvidence": evidence[:5],
        }
    except Exception:
        return base_context


async def run_orchestrator_stream(
    query: str, strategy: Strategy = "auto", llm_config: Optional[Dict[str, str]] = None
) -> AsyncGenerator[dict[str, Any], None]:
    started = time.monotonic()
    yield {"type": "status", "message": "开始执行，正在选择执行模式..."}
    mode, answer, _ = await run_orchestrator(query, strategy=strategy, llm_config=llm_config)
    yield {"type": "mode", "mode": mode, "message": f"已选择模式：{mode}"}
    yield {"type": "status", "message": "模式执行完成，正在整理输出..."}
    chunks = [line for line in answer.split("\n") if line.strip()]
    if not chunks:
        chunks = [answer]
    for line in chunks:
        yield {"type": "thought", "content": line}
    latency_ms = int((time.monotonic() - started) * 1000)
    yield {"type": "done", "mode": mode, "answer": answer, "latencyMs": latency_ms}


async def run_orchestrator_stream_for_step(
    base_query: str,
    step_text: str,
    step_index: int,
    total_steps: int,
    prior_summary: str,
    strategy: Union[Strategy, str] = "auto",
    llm_config: Optional[Dict[str, str]] = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """
    Stream a single plan step: composed prompt + prior step summaries.
    Emits the same event shapes as run_orchestrator_stream (ending with done).
    """
    composed = f"{base_query}\n\n[执行步骤 {step_index + 1}/{total_steps}]\n{step_text}\n"
    if prior_summary.strip():
        composed += f"\n[已完成步骤摘要]\n{prior_summary.strip()[:4000]}\n"
    strat: Strategy = strategy if strategy in ("auto", "agent", "react", "workflow") else "auto"
    async for evt in run_orchestrator_stream(composed, strategy=strat, llm_config=llm_config):
        yield evt

