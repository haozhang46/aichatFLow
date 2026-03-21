"""Optional ClawHub → local workspace sync stub (TASK-P2-04).

When enabled, registering a ClawHub slug creates a placeholder folder under the workspace
so UIs / agents have a stable path; replace with `clawhub install` subprocess if CLI is available.
"""

from __future__ import annotations

from pathlib import Path

from app.core.config import settings


def sync_clawhub_skill_stub(slug: str) -> dict:
    if not settings.clawhub_workspace_sync_enabled:
        return {"ok": True, "skipped": True, "reason": "CLAWHUB_WORKSPACE_SYNC_ENABLED is false"}
    root = (settings.clawhub_workspace_path or "").strip()
    if not root:
        return {"ok": False, "skipped": True, "reason": "CLAWHUB_WORKSPACE_PATH is empty"}
    base = Path(root).expanduser().resolve()
    skill_dir = base / "clawhub-skills" / slug
    skill_dir.mkdir(parents=True, exist_ok=True)
    readme = skill_dir / "README.txt"
    readme.write_text(
        f"ClawHub skill: {slug}\n"
        "This is a placeholder created by the gateway sync stub.\n"
        "Enable a real install flow or run `clawhub install {slug}` locally.\n",
        encoding="utf-8",
    )
    return {"ok": True, "path": str(skill_dir), "stub": True}
