"""
HTTP client for the public ClawHub registry API (same base URL as `clawhub` CLI --registry).

Docs: https://github.com/openclaw/clawhub/blob/main/docs/cli.md
Read-only search does not require auth; install/publish use GitHub login on the CLI side.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import settings


async def search_skills(query: str, limit: int = 25) -> dict[str, Any]:
    """GET /api/v1/search — vector search over published skills."""
    base = settings.clawhub_registry_url.rstrip("/")
    url = f"{base}/api/v1/search"
    params = {"q": query.strip(), "limit": max(1, min(limit, 100))}
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()
