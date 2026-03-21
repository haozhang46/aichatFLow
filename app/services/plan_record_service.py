from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
from typing import Any


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

    def find_latest_by_query(self, query: str) -> dict[str, Any] | None:
        normalized_query = self._normalize_query(query)
        if not normalized_query:
            return None
        candidates = sorted(self._plan_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        for path in candidates:
            parsed = self._parse_plan_record(path)
            if not parsed:
                continue
            if self._normalize_query(str(parsed.get("query", ""))) == normalized_query:
                return parsed
        return None

    def _build_tasks(self, plan_lines: list[str], mode: str, skills: list[str]) -> list[str]:
        skill_text = ", ".join(skills) if skills else "none"
        return [
            f"- Step {idx + 1}: {line} | agent: {mode} | skill: {skill_text}"
            for idx, line in enumerate(plan_lines)
        ]

    def _parse_plan_record(self, path: Path) -> dict[str, Any] | None:
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            return None

        lines = content.splitlines()
        if not lines or not lines[0].startswith("# Plan Record:"):
            return None

        query = lines[0].replace("# Plan Record:", "", 1).strip()
        mode_match = re.search(r"^- mode:\s*(.+)$", content, flags=re.MULTILINE)
        skills_match = re.search(r"^- skills:\s*(.+)$", content, flags=re.MULTILINE)
        intent = self._extract_section(content, "## 1. 用户意图描述", "## 2. 计划")
        plan_block = self._extract_section(content, "## 2. 计划", "## 3. task")
        supplement = self._extract_section(content, "## 补充说明", None)
        plan_lines = []
        for line in plan_block.splitlines():
            matched = re.match(r"^\s*\d+\.\s*(.+?)\s*$", line)
            if matched:
                plan_lines.append(matched.group(1).strip())

        skills_text = (skills_match.group(1).strip() if skills_match else "none").strip()
        recommended_skills = [] if skills_text.lower() == "none" else [s.strip() for s in skills_text.split(",") if s.strip()]
        return {
            "path": str(path),
            "query": query,
            "mode": mode_match.group(1).strip() if mode_match else "auto",
            "intentDescription": intent.strip() or f"用户希望解决：{query}",
            "planLines": plan_lines,
            "recommendedSkills": recommended_skills,
            "supplement": "" if supplement.strip().lower() == "none" else supplement.strip(),
        }

    def _extract_section(self, content: str, start_heading: str, end_heading: str | None) -> str:
        start = content.find(start_heading)
        if start < 0:
            return ""
        start += len(start_heading)
        if end_heading:
            end = content.find(end_heading, start)
            block = content[start:end if end >= 0 else None]
        else:
            block = content[start:]
        return block.strip()

    def _slugify(self, text: str) -> str:
        value = re.sub(r"\s+", "-", text.strip().lower())
        value = re.sub(r"[^a-z0-9\-_]+", "-", value)
        value = re.sub(r"-{2,}", "-", value).strip("-")
        return value[:48]

    def _normalize_query(self, text: str) -> str:
        return re.sub(r"\s+", " ", text.strip().lower())
