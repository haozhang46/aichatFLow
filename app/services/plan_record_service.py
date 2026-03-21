from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re


class PlanRecordService:
    def __init__(self) -> None:
        root = Path(__file__).resolve().parents[2]
        self._plan_dir = root / "specs" / "main" / "plans"
        self._plan_dir.mkdir(parents=True, exist_ok=True)

    def save_plan_record(
        self,
        *,
        query: str,
        intent_description: str,
        mode: str,
        plan_lines: list[str],
        recommended_skills: list[str],
        supplement: str,
    ) -> str:
        ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        slug = self._slugify(query) or "plan"
        filename = f"{ts}-{slug}.md"
        path = self._plan_dir / filename
        tasks = self._build_tasks(plan_lines, mode, recommended_skills)
        skills = ", ".join(recommended_skills) if recommended_skills else "none"
        supplement_value = supplement.strip() if supplement.strip() else "none"
        content = (
            f"# Plan Record: {query}\n\n"
            f"- request_time_utc: {datetime.utcnow().isoformat()}\n"
            f"- mode: {mode}\n"
            f"- skills: {skills}\n\n"
            "## 1. 用户意图描述\n\n"
            f"{intent_description}\n\n"
            "## 2. 计划\n\n"
            + ("\n".join(f"{idx + 1}. {line}" for idx, line in enumerate(plan_lines)) or "无")
            + "\n\n## 3. task\n\n"
            + ("\n".join(tasks) or "无")
            + f"\n\n## 补充说明\n\n{supplement_value}\n"
        )
        path.write_text(content, encoding="utf-8")
        return str(path)

    def _build_tasks(self, plan_lines: list[str], mode: str, skills: list[str]) -> list[str]:
        skill_text = ", ".join(skills) if skills else "none"
        return [
            f"- Step {idx + 1}: {line} | agent: {mode} | skill: {skill_text}"
            for idx, line in enumerate(plan_lines)
        ]

    def _slugify(self, text: str) -> str:
        value = re.sub(r"\s+", "-", text.strip().lower())
        value = re.sub(r"[^a-z0-9\-_]+", "-", value)
        value = re.sub(r"-{2,}", "-", value).strip("-")
        return value[:48]
