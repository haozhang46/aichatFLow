from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

from app.services.capability_service import CapabilityService

if TYPE_CHECKING:
    from app.services.metrics_service import MetricsService


class SkillExecutorService:
    def __init__(
        self, capability_service: CapabilityService, metrics_service: Optional["MetricsService"] = None
    ) -> None:
        self.capability_service = capability_service
        self._metrics = metrics_service

    def execute(self, skill_id: str, query: str) -> dict[str, Any]:
        if skill_id == "find-skills":
            skills = self.capability_service.list_skills(query=query)
            top = skills[:5]
            result = {
                "ok": True,
                "skill": skill_id,
                "summary": f"Matched {len(top)} skills for query",
                "data": [{"id": s["id"], "name": s["name"], "installed": s.get("installed", False)} for s in top],
            }
        else:
            result = {
                "ok": False,
                "skill": skill_id,
                "summary": f"skill `{skill_id}` executor not implemented",
                "data": [],
            }
        if self._metrics is not None:
            self._metrics.record_tool_call(ok=bool(result.get("ok")))
        return result
