from __future__ import annotations

from pathlib import Path
from typing import Any


class PersonalSkillTreeService:
    def __init__(self) -> None:
        project_root = Path(__file__).resolve().parents[2]
        self._root_path = project_root / "personal-skills"
        self._root_path.mkdir(parents=True, exist_ok=True)

    def get_root_path(self) -> str:
        return str(self._root_path)

    def set_root_path(self, path: str) -> dict[str, Any]:
        target = Path(path).expanduser()
        if not target.is_absolute():
            target = target.resolve()
        target.mkdir(parents=True, exist_ok=True)
        if not target.exists() or not target.is_dir():
            return {"ok": False, "message": f"invalid directory: {target}"}
        self._root_path = target
        return {"ok": True, "rootPath": str(self._root_path)}

    def list_tree(self) -> dict[str, Any]:
        root = self._root_path
        items: list[dict[str, str]] = []
        for entry in sorted(root.rglob("*"), key=lambda p: str(p.relative_to(root)).lower()):
            rel = str(entry.relative_to(root))
            if entry.is_dir():
                items.append({"type": "dir", "path": rel})
                continue
            if entry.is_file() and entry.suffix.lower() == ".md":
                items.append({"type": "md", "path": rel})
        return {"rootPath": str(root), "items": items}
