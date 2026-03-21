"""
Plan-time ClawHub discovery + lightweight risk hints (heuristic + optional LLM).

Full code review is not performed; users must still decide whether to enable a skill.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage
from langchain_core.prompts import ChatPromptTemplate

from app.core.config import settings
from app.services.clawhub_service import search_skills

logger = logging.getLogger(__name__)


def _extract_json_object(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:].strip()
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return json.loads(text[start : end + 1])
    return {}


def _heuristic_risk(slug: str, display_name: str, summary: str) -> dict[str, str]:
    blob = f"{slug} {display_name} {summary}".lower()
    high_kw = [
        "password",
        "credential",
        "token steal",
        "keylogger",
        "exfil",
        "steal",
        "wallet",
        "private key",
        "malware",
        "| bash",
        "curl |",
        "eval(",
        "child_process",
        "reverse shell",
    ]
    medium_kw = [
        "api key",
        "oauth",
        "sudo",
        "shell",
        "chmod 777",
        "webhook",
        "network",
        "download",
        "http://",
        "https://",
    ]
    risk = "low"
    if any(k in blob for k in high_kw):
        risk = "high"
    elif any(k in blob for k in medium_kw):
        risk = "medium"

    if risk == "high":
        rec = "avoid"
    elif risk == "medium":
        rec = "review"
    else:
        rec = "adopt"

    analysis = {
        "low": "根据名称/摘要未发现明显高危关键词；仍建议在安装前阅读 SKILL.md 与源码。",
        "medium": "摘要或名称涉及网络、凭据或命令执行等能力，请人工复核后再启用。",
        "high": "摘要或名称含高风险关键词（凭据窃取、远程执行等），不建议默认启用。",
    }[risk]
    return {"riskLevel": risk, "recommendation": rec, "analysis": analysis}


def _llm_available(llm_config: Optional[dict[str, str]]) -> bool:
    if llm_config and str(llm_config.get("apiKey", "")).strip():
        return True
    return bool(settings.openai_api_key and settings.openai_api_key.strip())


async def _enrich_with_llm(
    query: str,
    intent: str,
    plan_lines: list[str],
    items: list[dict[str, Any]],
    llm_config: Optional[dict[str, str]],
) -> list[dict[str, Any]]:
    if not items or not _llm_available(llm_config):
        return items
    api_key = (llm_config or {}).get("apiKey") or settings.openai_api_key
    base_url = (llm_config or {}).get("baseUrl") or settings.openai_base_url
    model = (llm_config or {}).get("model") or settings.openai_model
    llm = ChatOpenAI(
        api_key=api_key,
        base_url=base_url,
        model=model,
        temperature=0.1,
    )
    compact = [{"slug": x["slug"], "name": x["name"], "summary": x.get("summary", "")} for x in items]
    plan_text = "\n".join(f"{i + 1}. {line}" for i, line in enumerate(plan_lines))
    prompt = ChatPromptTemplate.from_messages(
        [
            SystemMessage(
                content=(
                    "You review ClawHub skill listings for a user plan. "
                    "You only see slug, name, and summary — not full code.\n"
                    "Return ONLY JSON:\n"
                    '{"items":[{"slug":"...","riskLevel":"low|medium|high",'
                    '"recommendation":"adopt|review|avoid","analysis":"one short sentence in Chinese"}]}\n'
                    "Rules:\n"
                    '- "avoid" if behavior could steal credentials, exfiltrate data, or persistently control the machine.\n'
                    '- "review" if network/shell/privileged access is likely but not clearly malicious.\n'
                    '- "adopt" only for clearly low-risk read-only or trivial helpers.\n'
                    "Align analysis with the user task when relevant."
                )
            ),
            (
                "human",
                "user_task={query}\nintent={intent}\nplan:\n{plan}\n\nskills:\n{skills_json}",
            ),
        ]
    )
    try:
        msg = prompt.format_messages(
            query=query,
            intent=intent,
            plan=plan_text,
            skills_json=json.dumps(compact, ensure_ascii=False),
        )
        raw = await llm.ainvoke(msg)
        content = str(getattr(raw, "content", "") or "")
        data = _extract_json_object(content)
        rows = data.get("items")
        if not isinstance(rows, list):
            return items
        by_slug = {str(r.get("slug", "")).strip(): r for r in rows if isinstance(r, dict)}
        merged: list[dict[str, Any]] = []
        for it in items:
            slug = it["slug"]
            row = by_slug.get(slug)
            if not row:
                merged.append(it)
                continue
            rl = str(row.get("riskLevel", "") or "").strip().lower()
            rec = str(row.get("recommendation", "") or "").strip().lower()
            an = str(row.get("analysis", "") or "").strip()
            if rl in ("low", "medium", "high"):
                it = {**it, "riskLevel": rl}
            if rec in ("adopt", "review", "avoid"):
                it = {**it, "recommendation": rec}
            if an:
                it = {**it, "analysis": an}
            merged.append(it)
        return merged
    except Exception as exc:
        logger.warning("ClawHub LLM analysis failed: %s", exc)
        return items


async def build_clawhub_plan_suggestions(
    query: str,
    intent: str,
    plan_lines: list[str],
    llm_config: Optional[dict[str, str]] = None,
    search_limit: int = 8,
) -> list[dict[str, Any]]:
    """
    Vector search on ClawHub + heuristic risk + optional LLM refinement.
    """
    try:
        raw = await search_skills(query, limit=max(3, min(search_limit, 20)))
    except Exception as exc:
        logger.warning("ClawHub search failed: %s", exc)
        return []
    results = raw.get("results") or []
    items: list[dict[str, Any]] = []
    for r in results[:search_limit]:
        slug = str(r.get("slug") or "").strip()
        if not slug:
            continue
        name = str(r.get("displayName") or slug)
        summary = str(r.get("summary") or "")
        score = r.get("score")
        h = _heuristic_risk(slug, name, summary)
        items.append(
            {
                "slug": slug,
                "name": name,
                "summary": summary,
                "score": score,
                "riskLevel": h["riskLevel"],
                "recommendation": h["recommendation"],
                "analysis": h["analysis"],
            }
        )
    if not items:
        return []
    return await _enrich_with_llm(query, intent, plan_lines, items, llm_config)
