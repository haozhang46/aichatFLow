from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from app.contracts.otie import ExecutionPlan


class PlanStore:
    def __init__(self, base_dir: Optional[Path] = None) -> None:
        root = Path(__file__).resolve().parents[2]
        self._dir = base_dir or (root / "data" / "otie" / "plans")
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, plan_id: str) -> Path:
        safe = "".join(c for c in plan_id if c.isalnum() or c in ("_", "-"))[:128] or "unknown"
        return self._dir / f"{safe}.json"

    def save(self, plan: ExecutionPlan) -> None:
        self._path(plan.plan_id).write_text(
            json.dumps(plan.model_dump(by_alias=True), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get(self, plan_id: str) -> Optional[ExecutionPlan]:
        path = self._path(plan_id)
        if not path.is_file():
            return None
        return ExecutionPlan.model_validate_json(path.read_text(encoding="utf-8"))
