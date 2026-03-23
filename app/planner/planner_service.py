from __future__ import annotations

import re
from typing import Optional

from app.core.config import settings
from app.contracts.otie import ExecutionPlan, IntentEnvelope, PlanStep
from app.memory.plan_store import PlanStore
from app.orchestrator.graph import build_plan_context
from app.services.capability_service import CapabilityService


class PlannerService:
    def __init__(self, capability_service: CapabilityService, plan_store: PlanStore) -> None:
        self._capability_service = capability_service
        self._plan_store = plan_store

    async def build_plan(self, intent: IntentEnvelope) -> ExecutionPlan:
        plan_context = await build_plan_context(
            intent.user_query,
            strategy=intent.mode_hint,
            llm_config=intent.llm_config,
        )
        mode = str(plan_context["mode"])
        recommended = self._capability_service.recommend(intent.user_query, mode)
        steps: list[PlanStep] = []
        rag_config = self._extract_rag_config(intent)

        if rag_config.get("enabled"):
            steps.append(
                PlanStep(
                    stepId=f"s{len(steps) + 1}",
                    kind="tool",
                    action=(
                        "Retrieve relevant knowledge from the tenant knowledge base"
                        + (f" within scope `{rag_config['scope']}`." if rag_config.get("scope") else ".")
                    ),
                    toolId="retrieval",
                    toolArgs={
                        "query": intent.user_query,
                        "tenantId": intent.tenant_id,
                        "scope": rag_config.get("scope"),
                        "topK": rag_config.get("topK", 5),
                        "minScore": rag_config.get("minScore", 0.12),
                    },
                    outputSchema={
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                            "scope": {"type": ["string", "null"]},
                            "topK": {"type": "number"},
                            "hits": {"type": "array"},
                        },
                        "required": ["query", "topK", "hits"],
                    },
                    agent="auto",
                )
            )

        weather_location = self._extract_weather_location(intent.user_query)
        if weather_location:
            steps.append(
                PlanStep(
                    stepId=f"s{len(steps) + 1}",
                    kind="tool",
                    action=f"Fetch current weather for `{weather_location}`.",
                    toolId="weather",
                    toolArgs={
                        "location": weather_location,
                        "query": intent.user_query,
                    },
                    outputSchema={
                        "type": "object",
                        "properties": {
                            "location": {"type": "object"},
                            "current": {"type": "object"},
                            "daily": {"type": "object"},
                        },
                        "required": ["location", "current", "daily"],
                    },
                    agent="auto",
                )
            )

        web_fetch_url = self._extract_web_fetch_url(intent.user_query)
        if web_fetch_url:
            steps.append(
                PlanStep(
                    stepId=f"s{len(steps) + 1}",
                    kind="tool",
                    action=f"Fetch and extract readable content from `{web_fetch_url}`.",
                    toolId="web-fetch",
                    toolArgs={
                        "url": web_fetch_url,
                        "maxChars": 12000,
                    },
                    outputSchema={
                        "type": "object",
                        "properties": {
                            "url": {"type": "string"},
                            "finalUrl": {"type": "string"},
                            "statusCode": {"type": "number"},
                            "title": {"type": "string"},
                            "contentType": {"type": "string"},
                            "content": {"type": "string"},
                        },
                        "required": ["url", "finalUrl", "statusCode", "title", "contentType", "content"],
                    },
                    agent="auto",
                )
            )

        if self._should_add_find_skills_tool(intent.user_query, recommended.get("recommendedSkills")):
            steps.append(
                PlanStep(
                    stepId=f"s{len(steps) + 1}",
                    kind="tool",
                    action="Search available skills related to the user request.",
                    dependsOn=[steps[-1].id] if steps else [],
                    toolId="find-skills",
                    toolArgs={"query": intent.user_query},
                    agent="auto",
                )
            )

        for skill_id in recommended.get("missingSkills", []):
            steps.append(
                PlanStep(
                    stepId=f"s{len(steps) + 1}",
                    kind="tool",
                    action=f"Install required skill `{skill_id}` before continuing.",
                    dependsOn=[steps[-1].id] if steps else [],
                    toolId="install-skill",
                    toolArgs={"skillId": skill_id},
                    agent="auto",
                )
            )

        offset = len(steps)
        for idx, line in enumerate(plan_context["plan"]):
            step_num = offset + idx + 1
            depends_on = [f"s{step_num - 1}"] if step_num > 1 else []
            steps.append(
                PlanStep(
                    stepId=f"s{step_num}",
                    kind="reason",
                    action=str(line).strip(),
                    dependsOn=depends_on,
                    agent=mode if mode in {"agent", "react", "workflow"} else "agent",
                )
            )

        final_dep = [steps[-1].id] if steps else []
        steps.append(
            PlanStep(
                stepId=f"s{len(steps) + 1}",
                kind="respond",
                action="Compose the final response from completed step outputs.",
                dependsOn=final_dep,
                agent="agent",
            )
        )

        plan = ExecutionPlan(
            intentId=intent.intent_id,
            mode=mode if mode in {"agent", "react", "workflow"} else "agent",
            status="ready",
            maxSteps=max(4, len(steps) + 2),
            steps=steps,
        )
        self._plan_store.save(plan)
        return plan

    def _should_add_find_skills_tool(self, query: str, recommended_skills: Optional[list[str]]) -> bool:
        q = query.lower()
        if "find-skills" in (recommended_skills or []):
            return True
        return any(token in q for token in ["skill", "skills", "capability", "安装", "能力", "插件"])

    def _extract_weather_location(self, query: str) -> str:
        q = query.strip()
        lowered = q.lower()
        weather_keywords = ["weather", "forecast", "temperature", "天气", "气温", "温度", "预报"]
        if not any(keyword in lowered for keyword in weather_keywords):
            return ""

        english_match = re.search(r"(?:weather|forecast|temperature)\s+(?:in|for)\s+([a-zA-Z\s,.-]+)", q, re.IGNORECASE)
        if english_match:
            return self._normalize_weather_location(english_match.group(1))

        chinese_match = re.search(r"(?:查询|查|看看|看下)?(.+?)(?:今天|今日|明天|天气|气温|温度|预报)", q)
        if chinese_match:
            candidate = self._normalize_weather_location(chinese_match.group(1))
            if candidate:
                return candidate

        return self._normalize_weather_location(q)

    def _normalize_weather_location(self, value: str) -> str:
        text = value.strip(" 在的，,。.?!")
        text = re.sub(r"\b(today|tomorrow|now|right now|this week)\b", "", text, flags=re.IGNORECASE)
        text = re.sub(r"(今天|今日|明天|现在|当前|这周)$", "", text)
        return text.strip(" ,.-")

    def _extract_rag_config(self, intent: IntentEnvelope) -> dict[str, object]:
        request_inputs = intent.constraints.get("requestInputs", {})
        if not isinstance(request_inputs, dict):
            return {"enabled": False}
        rag = request_inputs.get("rag")
        if not isinstance(rag, dict):
            return {"enabled": False}
        scope = str(rag.get("scope") or "").strip()
        enabled = bool(rag.get("enabled")) or bool(scope)
        top_k = rag.get("topK")
        min_score = rag.get("minScore")
        return {
            "enabled": enabled,
            "scope": scope or None,
            "topK": top_k if isinstance(top_k, int) and top_k > 0 else settings.rag_default_top_k,
            "minScore": float(min_score) if isinstance(min_score, (int, float)) else 0.12,
        }

    def _extract_web_fetch_url(self, query: str) -> str:
        q = query.strip()
        match = re.search(r"https?://[^\s)>\]}\"']+", q, re.IGNORECASE)
        if not match:
            return ""

        lowered = q.lower()
        fetch_keywords = [
            "read",
            "fetch",
            "open",
            "page",
            "website",
            "url",
            "link",
            "summarize",
            "crawl",
            "网页",
            "页面",
            "网址",
            "链接",
            "读取",
            "抓取",
            "总结",
            "看看",
            "打开",
        ]
        if any(keyword in lowered for keyword in fetch_keywords):
            return match.group(0).rstrip(".,;!?)]}")
        return ""
