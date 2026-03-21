from __future__ import annotations

from pathlib import Path
from typing import Optional

from app.services.skill_manifest import enrich_skill_record


class CapabilityService:
    def __init__(self) -> None:
        self._skill_roots = [
            Path.home() / ".codex" / "skills",
            Path.home() / ".cursor" / "skills",
            Path.home() / ".cursor" / "skills-cursor",
        ]
        self._curated_candidates = [
            {
                "id": "skill-installer",
                "name": "skill-installer",
                "source": "curated",
                "trusted": True,
                "tags": ["install", "catalog"],
                "installCommand": "install curated skill-installer",
            },
            {
                "id": "find-skills",
                "name": "find-skills",
                "source": "curated",
                "trusted": True,
                "tags": ["search", "discover"],
                "installCommand": "install curated find-skills",
            },
        ]
        self._online_catalog = [
            {
                "id": "weather-search-skill",
                "name": "weather-search-skill",
                "source": "github",
                "trusted": False,
                "tags": ["weather", "search"],
                "installCommand": "install github/weather-search-skill",
            },
            {
                "id": "planner-assistant-skill",
                "name": "planner-assistant-skill",
                "source": "github",
                "trusted": False,
                "tags": ["planner", "workflow"],
                "installCommand": "install github/planner-assistant-skill",
            },
        ]
        self._install_whitelist = {item["id"] for item in self._curated_candidates if item["trusted"]}
        self._runtime_installed_skills: set[str] = set()

    def list_agents(self, query: Optional[str] = None) -> list[dict]:
        agents = [
            {
                "id": "agent",
                "label": "Direct Agent",
                "description": "Direct answer mode for broad tasks.",
                "category": "built-in",
                "available": True,
            },
            {
                "id": "react",
                "label": "ReAct",
                "description": "Thought/action/observation reasoning mode.",
                "category": "built-in",
                "available": True,
            },
            {
                "id": "workflow",
                "label": "Workflow",
                "description": "Plan-first workflow style execution mode.",
                "category": "built-in",
                "available": True,
            },
        ]
        if query:
            q = query.strip().lower()
            agents = [
                a
                for a in agents
                if q in a["id"].lower()
                or q in a["label"].lower()
                or q in a["description"].lower()
            ]
        return agents

    def list_skills(self, query: Optional[str] = None) -> list[dict]:
        installed = self._collect_local_skills()
        installed_ids = {s["id"] for s in installed}
        installed_ids.update(self._runtime_installed_skills)
        curated = [
            {
                **c,
                "installed": c["id"] in installed_ids,
                "version": "",
                "whitelisted": c["id"] in self._install_whitelist,
            }
            for c in self._curated_candidates
        ]
        results = sorted(installed + curated, key=lambda x: (not x["installed"], x["name"]))
        if query:
            q = query.strip().lower()
            results = [s for s in results if q in s["id"].lower() or q in s["name"].lower()]
        return [enrich_skill_record(s) for s in results]

    def list_skills_paginated(self, query: Optional[str], page: int, page_size: int) -> dict:
        all_skills = self.list_skills(query=query)
        total = len(all_skills)
        start = max(0, (page - 1) * page_size)
        end = start + page_size
        return {
            "items": all_skills[start:end],
            "total": total,
            "page": page,
            "pageSize": page_size,
        }

    def recommend(self, query: str, mode: str) -> dict:
        q = query.lower()
        recommended: list[str] = []
        if any(k in q for k in ["skill", "agent", "配置", "安装", "install"]):
            recommended.append("find-skills")
        if any(k in q for k in ["天气", "weather", "search", "查"]):
            recommended.append("find-skills")
        if mode == "workflow":
            recommended.append("skill-installer")
        recommended = sorted(set(recommended))
        installed_ids = {s["id"] for s in self.list_skills() if s.get("installed")}
        missing = [sid for sid in recommended if sid not in installed_ids]
        return {
            "recommendedAgent": mode,
            "recommendedSkills": recommended,
            "missingSkills": missing,
            "installRequired": len(missing) > 0,
        }

    def _collect_local_skills(self) -> list[dict]:
        items: list[dict] = []
        for root in self._skill_roots:
            if not root.exists():
                continue
            for entry in root.iterdir():
                if not entry.is_dir():
                    continue
                skill_md = entry / "SKILL.md"
                if not skill_md.exists():
                    continue
                items.append(
                    {
                        "id": entry.name,
                        "name": entry.name,
                        "source": "local",
                        "installed": True,
                        "trusted": True,
                        "version": "",
                        "tags": [],
                        "installCommand": "",
                    }
                )
        return items

    def get_skill(self, skill_id: str) -> dict | None:
        for skill in self.list_skills():
            if skill["id"] == skill_id:
                return skill
        return None

    def install_events_for_missing(self, missing_skills: list[str], auto_install: bool) -> list[dict]:
        events: list[dict] = []
        if not missing_skills:
            return events
        if not auto_install:
            events.append(
                {
                    "type": "status",
                    "message": f"检测到缺失 skills: {', '.join(missing_skills)}，未启用自动安装，跳过安装。",
                }
            )
            return events

        for skill_id in missing_skills:
            skill = self.get_skill(skill_id)
            if not skill:
                events.append({"type": "status", "message": f"skill `{skill_id}` 未在目录中注册，跳过。"})
                continue
            if skill.get("installed"):
                events.append({"type": "status", "message": f"skill `{skill_id}` 已安装，跳过。"})
                continue
            if skill_id not in self._install_whitelist:
                events.append({"type": "status", "message": f"skill `{skill_id}` 不在白名单，拒绝自动安装。"})
                continue
            command = skill.get("installCommand") or "N/A"
            events.append({"type": "status", "message": f"开始安装 skill `{skill_id}`..."})
            # Guarded simulation in API layer: only whitelisted IDs are allowed.
            events.append({"type": "install", "skill": skill_id, "status": "installed", "command": command})
            self._runtime_installed_skills.add(skill_id)
            events.append({"type": "status", "message": f"skill `{skill_id}` 安装完成。"})
        return events

    def install_skill(self, skill_id: str) -> dict:
        skill = self.get_skill(skill_id)
        if not skill:
            return {"ok": False, "message": f"skill `{skill_id}` 不存在"}
        if skill.get("installed"):
            return {"ok": True, "message": f"skill `{skill_id}` 已安装"}
        if skill_id not in self._install_whitelist:
            return {"ok": False, "message": f"skill `{skill_id}` 不在白名单，禁止安装"}
        self._runtime_installed_skills.add(skill_id)
        return {"ok": True, "message": f"skill `{skill_id}` 安装成功"}

    def list_whitelist(self) -> list[str]:
        return sorted(self._install_whitelist)

    def set_whitelist(self, skill_id: str, enabled: bool) -> dict:
        skill = self.get_skill(skill_id)
        if not skill:
            return {"ok": False, "message": f"skill `{skill_id}` 不存在"}
        if enabled:
            self._install_whitelist.add(skill_id)
        else:
            self._install_whitelist.discard(skill_id)
        return {"ok": True, "whitelisted": skill_id in self._install_whitelist}

    def search_online_skills(self, query: str) -> list[dict]:
        q = query.strip().lower()
        if not q:
            return []
        installed_ids = {s["id"] for s in self.list_skills()}
        results = []
        for item in self._online_catalog:
            hay = " ".join([item["id"], item["name"], " ".join(item.get("tags", []))]).lower()
            if q in hay:
                results.append(
                    {
                        **item,
                        "installed": item["id"] in installed_ids,
                        "whitelisted": item["id"] in self._install_whitelist,
                    }
                )
        return results

    def add_online_skill(self, skill_id: str) -> dict:
        for item in self._online_catalog:
            if item["id"] == skill_id:
                if not any(c["id"] == skill_id for c in self._curated_candidates):
                    self._curated_candidates.append(item.copy())
                return {"ok": True, "message": f"已加入可用列表: {skill_id}"}
        return {"ok": False, "message": f"未找到在线 skill: {skill_id}"}

    def register_clawhub_skill(self, slug: str, display_name: str = "", summary: str = "") -> dict:
        """Add a ClawHub skill slug to the in-process curated list (whitelist/install flows)."""
        slug = slug.strip()
        if not slug:
            return {"ok": False, "message": "slug 不能为空"}
        if any(c["id"] == slug for c in self._curated_candidates):
            return {"ok": True, "message": f"已在可用列表: {slug}"}
        self._curated_candidates.append(
            {
                "id": slug,
                "name": display_name.strip() or slug,
                "source": "clawhub",
                "trusted": False,
                "tags": ["clawhub"],
                "installCommand": f"clawhub install {slug}",
            }
        )
        try:
            from app.services.clawhub_workspace_sync import sync_clawhub_skill_stub

            sync = sync_clawhub_skill_stub(slug)
        except Exception:  # pragma: no cover
            sync = {"ok": False, "skipped": True}
        return {
            "ok": True,
            "message": f"已加入可用列表（ClawHub）: {slug}",
            "summary": summary,
            "workspaceSync": sync,
        }
