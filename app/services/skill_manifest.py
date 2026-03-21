"""
Unified tool/skill manifest (TASK-P2-03).

Merged into capability list responses for UI and policy.
"""

from __future__ import annotations

from typing import Any

# Minimal built-in manifests; extend per skill or load from SKILL.md frontmatter later.
_DEFAULT = {
    "toolId": "",
    "riskLevel": "medium",
    "source": "unknown",
    "permissions": [],
    "inputSchema": {"type": "object", "additionalProperties": True},
    "outputSchema": {"type": "object", "additionalProperties": True},
}

SKILL_MANIFESTS: dict[str, dict[str, Any]] = {
    "find-skills": {
        "toolId": "find-skills",
        "riskLevel": "low",
        "source": "curated",
        "permissions": ["capability:list"],
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
        "outputSchema": {
            "type": "object",
            "properties": {
                "ok": {"type": "boolean"},
                "summary": {"type": "string"},
                "data": {"type": "array"},
            },
        },
    },
    "skill-installer": {
        "toolId": "skill-installer",
        "riskLevel": "medium",
        "source": "curated",
        "permissions": ["skill:install"],
        "inputSchema": {"type": "object", "properties": {"skillId": {"type": "string"}}},
        "outputSchema": {"type": "object"},
    },
    "weather-search-skill": {
        "toolId": "weather-search-skill",
        "riskLevel": "low",
        "source": "github",
        "permissions": ["network:read"],
        "inputSchema": {"type": "object"},
        "outputSchema": {"type": "object"},
    },
    "planner-assistant-skill": {
        "toolId": "planner-assistant-skill",
        "riskLevel": "low",
        "source": "github",
        "permissions": [],
        "inputSchema": {"type": "object"},
        "outputSchema": {"type": "object"},
    },
}


def build_manifest_for_skill(skill_id: str, source: str) -> dict[str, Any]:
    base = dict(_DEFAULT)
    base["toolId"] = skill_id
    base["source"] = source
    extra = SKILL_MANIFESTS.get(skill_id, {})
    merged = {**base, **extra}
    merged["toolId"] = extra.get("toolId") or skill_id
    return merged


def enrich_skill_record(skill: dict[str, Any]) -> dict[str, Any]:
    sid = str(skill.get("id") or "")
    src = str(skill.get("source") or "unknown")
    manifest = build_manifest_for_skill(sid, src)
    return {**skill, "manifest": manifest}
