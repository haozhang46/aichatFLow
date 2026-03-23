from __future__ import annotations

from pathlib import Path
from typing import Any


class FileService:
    def __init__(self) -> None:
        root = Path(__file__).resolve().parents[2]
        self._stories_root = root / "stories"
        self._stories_root.mkdir(parents=True, exist_ok=True)

    def read(self, path: str) -> dict[str, Any]:
        target = self._resolve_path(path)
        if target.is_dir():
            return {
                "path": self._relative_path(target),
                "type": "dir",
                "items": [
                    {
                        "name": child.name,
                        "path": self._relative_path(child),
                        "type": "dir" if child.is_dir() else "file",
                    }
                    for child in sorted(target.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
                ],
            }
        if not target.exists() or not target.is_file():
            raise ValueError("file not found")
        return {
            "path": self._relative_path(target),
            "type": "file",
            "content": target.read_text(encoding="utf-8"),
        }

    def list_tree(self, path: str = "") -> dict[str, Any]:
        target = self._resolve_path(path, allow_missing=False)
        if not target.exists() or not target.is_dir():
            raise ValueError("directory not found")
        items: list[dict[str, str]] = []
        for entry in sorted(target.rglob("*"), key=lambda item: str(item.relative_to(target)).lower()):
            items.append(
                {
                    "path": self._relative_path(entry),
                    "type": "dir" if entry.is_dir() else "file",
                }
            )
        return {"rootPath": self._relative_path(target), "items": items}

    def write(self, path: str, content: str) -> dict[str, Any]:
        target = self._resolve_path(path)
        if target.suffix == "":
            raise ValueError("path must be a file")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return {"path": self._relative_path(target), "type": "file", "saved": True}

    def mkdir(self, path: str) -> dict[str, Any]:
        target = self._resolve_path(path)
        if target.suffix:
            raise ValueError("path must be a directory")
        target.mkdir(parents=True, exist_ok=True)
        return {"path": self._relative_path(target), "type": "dir", "created": True}

    def patch(self, path: str, content: str, *, mode: str = "append") -> dict[str, Any]:
        target = self._resolve_path(path)
        if target.suffix == "":
            raise ValueError("path must be a file")
        normalized_mode = mode.strip().lower()
        if normalized_mode not in {"replace", "append", "prepend"}:
            raise ValueError("patch mode must be one of: replace, append, prepend")
        existing = ""
        if target.exists():
            if target.is_dir():
                raise ValueError("path must be a file")
            existing = target.read_text(encoding="utf-8")
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
        if normalized_mode == "replace":
            next_content = content
        elif normalized_mode == "prepend":
            next_content = f"{content}{existing}"
        else:
            next_content = f"{existing}{content}"
        target.write_text(next_content, encoding="utf-8")
        return {
            "path": self._relative_path(target),
            "type": "file",
            "patched": True,
            "mode": normalized_mode,
            "size": len(next_content),
        }

    def delete(self, path: str) -> dict[str, Any]:
        target = self._resolve_path(path)
        if not target.exists():
            raise ValueError("path not found")
        if target.is_dir():
            if any(target.iterdir()):
                raise ValueError("directory is not empty")
            target.rmdir()
            return {"path": self._relative_path(target), "deleted": True, "type": "dir"}
        target.unlink()
        return {"path": self._relative_path(target), "deleted": True, "type": "file"}

    def resolve_relative(self, path: str) -> str:
        return self._relative_path(self._resolve_path(path))

    def _resolve_path(self, path: str, *, allow_missing: bool = True) -> Path:
        raw = path.strip().replace("\\", "/").strip("/")
        candidate = (self._stories_root / raw).resolve()
        root = self._stories_root.resolve()
        if candidate != root and root not in candidate.parents:
            raise ValueError("path escapes allowed root")
        if not allow_missing and not candidate.exists():
            raise ValueError("path not found")
        return candidate

    def _relative_path(self, path: Path) -> str:
        try:
            rel = path.resolve().relative_to(self._stories_root.resolve())
        except ValueError:
            return ""
        return f"stories/{rel.as_posix()}".rstrip("/")
