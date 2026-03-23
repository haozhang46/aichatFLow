from __future__ import annotations

from html import unescape
import re
from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.config import settings
from app.services.capability_service import CapabilityService
from app.services.file_acl_service import FileAclService
from app.services.file_service import FileService
from app.services.platform_trace_service import PlatformTraceService
from app.services.rag_service import RagService
from app.services.skill_executor_service import SkillExecutorService


class FindSkillsTool:
    tool_id = "find-skills"
    display_name = "Find Skills"
    description = "Search locally known skills and return a short ranked list."
    category = "discovery"
    input_schema = {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}
    example_args = {"query": "workflow automation"}

    def __init__(self, capability_service: CapabilityService) -> None:
        self._capability_service = capability_service

    async def execute(self, args: dict[str, Any]) -> dict[str, Any]:
        query = str(args.get("query", "")).strip()
        skills = self._capability_service.list_skills(query=query)[:5]
        return {
            "query": query,
            "count": len(skills),
            "items": [
                {
                    "id": skill["id"],
                    "name": skill["name"],
                    "installed": bool(skill.get("installed")),
                    "source": skill.get("source"),
                }
                for skill in skills
            ],
        }


class InstallSkillTool:
    tool_id = "install-skill"
    display_name = "Install Skill"
    description = "Install a whitelisted skill into the local runtime catalog."
    category = "governance"
    input_schema = {"type": "object", "properties": {"skillId": {"type": "string"}}, "required": ["skillId"]}
    example_args = {"skillId": "find-skills"}

    def __init__(self, capability_service: CapabilityService) -> None:
        self._capability_service = capability_service

    async def execute(self, args: dict[str, Any]) -> dict[str, Any]:
        skill_id = str(args.get("skillId", "")).strip()
        if not skill_id:
            raise ValueError("skillId is required")
        return self._capability_service.install_skill(skill_id)


class ExecuteSkillTool:
    tool_id = "execute-skill"
    display_name = "Execute Skill"
    description = "Run a registered skill executor against a query."
    category = "execution"
    input_schema = {
        "type": "object",
        "properties": {"skillId": {"type": "string"}, "query": {"type": "string"}},
        "required": ["skillId", "query"],
    }
    example_args = {"skillId": "find-skills", "query": "find local tools"}

    def __init__(self, skill_executor_service: SkillExecutorService) -> None:
        self._skill_executor_service = skill_executor_service

    async def execute(self, args: dict[str, Any]) -> dict[str, Any]:
        skill_id = str(args.get("skillId", "")).strip()
        query = str(args.get("query", "")).strip()
        if not skill_id:
            raise ValueError("skillId is required")
        return self._skill_executor_service.execute(skill_id, query)


class WeatherTool:
    tool_id = "weather"
    display_name = "Weather"
    description = "Resolve a location and fetch current weather plus same-day forecast."
    category = "data"
    ui_plugin = "weather-query"
    input_schema = {
        "type": "object",
        "properties": {
            "location": {"type": "string"},
            "query": {"type": "string"},
            "temperatureUnit": {"type": "string"},
        },
    }
    output_schema = {
        "type": "object",
        "properties": {
            "location": {"type": "object"},
            "current": {"type": "object"},
            "daily": {"type": "object"},
        },
    }
    ui_schema = {
        "layout": "form",
        "fields": [
            {"key": "location", "label": "Location", "component": "input", "placeholder": "Shanghai"},
            {"key": "query", "label": "Query", "component": "textarea", "placeholder": "What is the weather in Shanghai today?", "rows": 3},
            {"key": "temperatureUnit", "label": "Temperature Unit", "component": "select", "options": [
                {"label": "Celsius", "value": "celsius"},
                {"label": "Fahrenheit", "value": "fahrenheit"},
            ]},
        ],
    }
    required_user_inputs = [
        {
            "key": "location",
            "label": "Location",
            "type": "text",
            "required": True,
            "secret": False,
            "placeholder": "Shanghai",
        }
    ]
    example_args = {"location": "Shanghai", "temperatureUnit": "celsius"}

    async def execute(self, args: dict[str, Any]) -> dict[str, Any]:
        location = self._extract_location(args)
        unit = str(args.get("temperatureUnit") or "celsius").strip().lower()
        if unit not in {"celsius", "fahrenheit"}:
            unit = "celsius"

        async with httpx.AsyncClient(timeout=10.0) as client:
            geo_resp = await client.get(
                settings.weather_geocode_base_url,
                params={"name": location, "count": 1, "language": "en", "format": "json"},
            )
            geo_resp.raise_for_status()
            geo_data = geo_resp.json()
            results = geo_data.get("results") or []
            if not results:
                raise ValueError(f"location `{location}` not found")
            top = results[0]

            forecast_resp = await client.get(
                settings.weather_forecast_base_url,
                params={
                    "latitude": top["latitude"],
                    "longitude": top["longitude"],
                    "current": "temperature_2m,apparent_temperature,wind_speed_10m,weather_code",
                    "daily": "weather_code,temperature_2m_max,temperature_2m_min",
                    "timezone": "auto",
                    "forecast_days": 1,
                    "temperature_unit": unit,
                },
            )
            forecast_resp.raise_for_status()
            forecast = forecast_resp.json()

        daily = forecast.get("daily") or {}
        current = forecast.get("current") or {}
        return {
            "location": {
                "query": location,
                "name": top.get("name"),
                "country": top.get("country"),
                "admin1": top.get("admin1"),
                "latitude": top.get("latitude"),
                "longitude": top.get("longitude"),
                "timezone": forecast.get("timezone"),
            },
            "current": {
                "temperature": current.get("temperature_2m"),
                "apparentTemperature": current.get("apparent_temperature"),
                "windSpeed": current.get("wind_speed_10m"),
                "weatherCode": current.get("weather_code"),
                "temperatureUnit": forecast.get("current_units", {}).get("temperature_2m"),
                "windSpeedUnit": forecast.get("current_units", {}).get("wind_speed_10m"),
            },
            "daily": {
                "date": (daily.get("time") or [None])[0],
                "temperatureMax": (daily.get("temperature_2m_max") or [None])[0],
                "temperatureMin": (daily.get("temperature_2m_min") or [None])[0],
                "weatherCode": (daily.get("weather_code") or [None])[0],
            },
        }

    def _extract_location(self, args: dict[str, Any]) -> str:
        location = str(args.get("location") or "").strip()
        if location:
            return location
        query = str(args.get("query") or "").strip()
        if not query:
            raise ValueError("location or query is required")
        return self._location_from_query(query)

    def _location_from_query(self, query: str) -> str:
        text = query.strip().rstrip("?.!")
        lowered = text.lower()
        english_patterns = [
            r"(?:weather|forecast)\s+(?:in|for)\s+([a-zA-Z\s,.-]+)$",
            r"(?:in)\s+([a-zA-Z\s,.-]+)\s+(?:weather|forecast)$",
        ]
        for pattern in english_patterns:
            match = re.search(pattern, lowered, re.IGNORECASE)
            if match:
                return self._normalize_location(text[match.start(1) : match.end(1)])

        chinese_match = re.search(r"(?:查询|查|看看|看下)?(.+?)(?:今天|今日|明天|天气|气温|温度|预报)", text)
        if chinese_match:
            candidate = self._normalize_location(chinese_match.group(1))
            if candidate:
                return candidate

        return self._normalize_location(text)

    def _normalize_location(self, value: str) -> str:
        text = value.strip(" 在的，,。.?!")
        text = re.sub(r"\b(today|tomorrow|now|right now|this week)\b", "", text, flags=re.IGNORECASE)
        text = re.sub(r"(今天|今日|明天|现在|当前|这周)$", "", text)
        return text.strip(" ,.-")


class RetrievalTool:
    tool_id = "retrieval"
    display_name = "Retrieval"
    description = "Search tenant-scoped knowledge with optional RAG scope filtering."
    category = "knowledge"
    ui_plugin = "rag-retrieval"
    input_schema = {
        "type": "object",
        "properties": {
            "tenantId": {"type": "string"},
            "query": {"type": "string"},
            "scope": {"type": "string"},
            "topK": {"type": "number"},
            "minScore": {"type": "number"},
        },
        "required": ["tenantId", "query"],
    }
    ui_schema = {
        "layout": "form",
        "fields": [
            {"key": "tenantId", "label": "Tenant", "component": "input", "placeholder": "tenant-a"},
            {"key": "query", "label": "Query", "component": "textarea", "placeholder": "输入要检索的问题", "rows": 4},
            {"key": "scope", "label": "Scope", "component": "scope-select", "placeholder": "All scopes"},
            {"key": "topK", "label": "Top K", "component": "number", "min": 1, "step": 1},
            {"key": "minScore", "label": "Min Score", "component": "number", "min": 0, "max": 1, "step": 0.01},
        ],
        "actions": [
            {"key": "open-rag-viewer", "label": "Open RAG Viewer", "type": "client"},
        ],
    }
    required_user_inputs = [
        {
            "key": "scope",
            "label": "RAG Scope",
            "type": "text",
            "required": False,
            "secret": False,
            "placeholder": "refund-policy",
        }
    ]
    example_args = {"tenantId": "tenant-a", "query": "退款规则", "scope": "refund-policy", "topK": 5}

    def __init__(self, rag_service: RagService) -> None:
        self._rag_service = rag_service

    async def execute(self, args: dict[str, Any]) -> dict[str, Any]:
        query = str(args.get("query") or "").strip()
        tenant_id = str(args.get("tenantId") or "tenant-a").strip() or "tenant-a"
        scope_raw = args.get("scope")
        scope = str(scope_raw).strip() if isinstance(scope_raw, str) else None
        top_k_raw = args.get("topK")
        min_score_raw = args.get("minScore")
        top_k = top_k_raw if isinstance(top_k_raw, int) and top_k_raw > 0 else 5
        min_score = min_score_raw if isinstance(min_score_raw, (int, float)) else 0.12
        result = await self._rag_service.search(
            tenant_id=tenant_id,
            query=query,
            scope=scope,
            top_k=top_k,
            min_score=float(min_score),
        )
        result["tenantId"] = tenant_id
        return result


class WebFetchTool:
    tool_id = "web-fetch"
    display_name = "Web Fetch"
    description = "Fetch a web page and extract basic readable text content."
    category = "web"
    ui_plugin = "web-fetch"
    input_schema = {
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "maxChars": {"type": "number"},
        },
        "required": ["url"],
    }
    ui_schema = {
        "layout": "form",
        "fields": [
            {"key": "url", "label": "URL", "component": "input", "placeholder": "https://example.com"},
            {"key": "maxChars", "label": "Max Chars", "component": "number", "min": 100, "step": 100},
        ],
    }
    output_schema = {
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "finalUrl": {"type": "string"},
            "statusCode": {"type": "number"},
            "title": {"type": "string"},
            "contentType": {"type": "string"},
            "content": {"type": "string"},
        },
        "required": ["url", "finalUrl", "statusCode", "title", "contentType", "content"],
    }
    required_user_inputs = [
        {
            "key": "url",
            "label": "URL",
            "type": "text",
            "required": True,
            "secret": False,
            "placeholder": "https://example.com/page",
        }
    ]
    example_args = {"url": "https://example.com", "maxChars": 4000}

    async def execute(self, args: dict[str, Any]) -> dict[str, Any]:
        url = str(args.get("url") or "").strip()
        if not url:
            raise ValueError("url is required")
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("url must use http or https")

        max_chars_raw = args.get("maxChars")
        max_chars = max_chars_raw if isinstance(max_chars_raw, int) and max_chars_raw > 0 else 12000

        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.get(
                url,
                headers={
                    "User-Agent": "aichatFlow/1.0 (+https://localhost/otie)",
                    "Accept": "text/html,application/xhtml+xml",
                },
            )
            response.raise_for_status()

        html = response.text
        title = self._extract_title(html)
        content = self._extract_content(html, max_chars=max_chars)
        return {
            "url": url,
            "finalUrl": str(response.url),
            "statusCode": response.status_code,
            "title": title,
            "contentType": response.headers.get("content-type", ""),
            "content": content,
        }

    def _extract_title(self, html: str) -> str:
        match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
        if not match:
            return ""
        title = unescape(match.group(1))
        return re.sub(r"\s+", " ", title).strip()

    def _extract_content(self, html: str, *, max_chars: int) -> str:
        cleaned = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", html)
        cleaned = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", cleaned)
        cleaned = re.sub(r"(?is)<noscript[^>]*>.*?</noscript>", " ", cleaned)
        cleaned = re.sub(r"(?i)</(p|div|section|article|main|h1|h2|h3|h4|h5|h6|li|br|tr|td)>", "\n", cleaned)
        cleaned = re.sub(r"(?s)<[^>]+>", " ", cleaned)
        cleaned = unescape(cleaned)
        cleaned = re.sub(r"[ \t\r\f\v]+", " ", cleaned)
        cleaned = re.sub(r"\n\s*\n+", "\n\n", cleaned)
        text = cleaned.strip()
        return text[:max_chars]


class FileListTool:
    tool_id = "file-list"
    display_name = "File List"
    description = "List files under the stories workspace if the current user has read permission."
    category = "filesystem"
    input_schema = {
        "type": "object",
        "properties": {"path": {"type": "string"}},
    }
    example_args = {"path": "demo"}

    def __init__(
        self,
        file_service: FileService,
        file_acl_service: FileAclService,
        platform_trace_service: PlatformTraceService,
    ) -> None:
        self._file_service = file_service
        self._file_acl_service = file_acl_service
        self._platform_trace_service = platform_trace_service

    async def execute(self, args: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
        user_id = self._current_user(context)
        path = str(args.get("path") or "").strip()
        acl_path = f"stories/{path}".rstrip("/") if path else "stories/"
        if not self._file_acl_service.is_allowed(user_id, acl_path, "read"):
            self._emit_trace("acl_denied", user_id=user_id, resource_path=acl_path, metadata={"action": "read"})
            raise ValueError(f"read access denied for `{acl_path}`")
        result = self._file_service.list_tree(path)
        self._emit_trace("file_read", user_id=user_id, resource_path=acl_path, metadata={"action": "list_tree"})
        return result

    def _current_user(self, context: dict[str, Any] | None) -> str:
        user_id = str((context or {}).get("currentUserId") or "").strip()
        if not user_id:
            raise ValueError("current user context is missing")
        return user_id

    def _emit_trace(
        self,
        event_type: str,
        *,
        user_id: str,
        resource_path: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        trace_id = self._platform_trace_service.new_trace_id("file")
        self._platform_trace_service.emit(
            trace_id,
            event_type,
            run_id=trace_id,
            status="success" if event_type != "acl_denied" else "failed",
            userId=user_id,
            resourcePath=resource_path,
            metadata=metadata or {},
        )


class FileReadTool(FileListTool):
    tool_id = "file-read"
    display_name = "File Read"
    description = "Read a file or directory under the stories workspace if the current user has read permission."
    category = "filesystem"
    input_schema = {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    }
    example_args = {"path": "demo/test.md"}

    async def execute(self, args: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
        user_id = self._current_user(context)
        path = str(args.get("path") or "").strip()
        if not path:
            raise ValueError("path is required")
        acl_path = f"stories/{path}"
        if not self._file_acl_service.is_allowed(user_id, acl_path, "read"):
            self._emit_trace("acl_denied", user_id=user_id, resource_path=acl_path, metadata={"action": "read"})
            raise ValueError(f"read access denied for `{acl_path}`")
        result = self._file_service.read(path)
        self._emit_trace("file_read", user_id=user_id, resource_path=acl_path, metadata={"action": "read"})
        return result


class FileWriteTool(FileListTool):
    tool_id = "file-write"
    display_name = "File Write"
    description = "Write a file under the stories workspace if the current user has write permission."
    category = "filesystem"
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "content": {"type": "string"},
        },
        "required": ["path", "content"],
    }
    example_args = {"path": "demo/test.md", "content": "# hello"}

    async def execute(self, args: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
        user_id = self._current_user(context)
        path = str(args.get("path") or "").strip()
        content = str(args.get("content") or "")
        if not path:
            raise ValueError("path is required")
        acl_path = f"stories/{path}"
        if not self._file_acl_service.is_allowed(user_id, acl_path, "write"):
            self._emit_trace("acl_denied", user_id=user_id, resource_path=acl_path, metadata={"action": "write"})
            raise ValueError(f"write access denied for `{acl_path}`")
        result = self._file_service.write(path, content)
        self._emit_trace("file_write", user_id=user_id, resource_path=acl_path, metadata={"action": "write"})
        return result


class FileDeleteTool(FileListTool):
    tool_id = "file-delete"
    display_name = "File Delete"
    description = "Delete a file under the stories workspace if the current user has delete permission."
    category = "filesystem"
    input_schema = {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    }
    example_args = {"path": "demo/test.md"}

    async def execute(self, args: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
        user_id = self._current_user(context)
        path = str(args.get("path") or "").strip()
        if not path:
            raise ValueError("path is required")
        acl_path = f"stories/{path}"
        if not self._file_acl_service.is_allowed(user_id, acl_path, "delete"):
            self._emit_trace("acl_denied", user_id=user_id, resource_path=acl_path, metadata={"action": "delete"})
            raise ValueError(f"delete access denied for `{acl_path}`")
        result = self._file_service.delete(path)
        self._emit_trace("file_delete", user_id=user_id, resource_path=acl_path, metadata={"action": "delete"})
        return result


class FileMkdirTool(FileListTool):
    tool_id = "file-mkdir"
    display_name = "File Mkdir"
    description = "Create a directory under the stories workspace if the current user has write permission."
    category = "filesystem"
    input_schema = {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    }
    example_args = {"path": "demo/chapter-notes"}

    async def execute(self, args: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
        user_id = self._current_user(context)
        path = str(args.get("path") or "").strip()
        if not path:
            raise ValueError("path is required")
        acl_path = f"stories/{path}"
        if not self._file_acl_service.is_allowed(user_id, acl_path, "write"):
            self._emit_trace("acl_denied", user_id=user_id, resource_path=acl_path, metadata={"action": "mkdir"})
            raise ValueError(f"write access denied for `{acl_path}`")
        result = self._file_service.mkdir(path)
        self._emit_trace("file_mkdir", user_id=user_id, resource_path=acl_path, metadata={"action": "mkdir"})
        return result


class FilePatchTool(FileListTool):
    tool_id = "file-patch"
    display_name = "File Patch"
    description = "Patch a file under the stories workspace using replace, append, or prepend mode."
    category = "filesystem"
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "content": {"type": "string"},
            "mode": {"type": "string", "enum": ["replace", "append", "prepend"]},
        },
        "required": ["path", "content"],
    }
    example_args = {"path": "demo/test.md", "content": "\n## Next\n", "mode": "append"}

    async def execute(self, args: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
        user_id = self._current_user(context)
        path = str(args.get("path") or "").strip()
        content = str(args.get("content") or "")
        mode = str(args.get("mode") or "append").strip().lower()
        if not path:
            raise ValueError("path is required")
        acl_path = f"stories/{path}"
        if not self._file_acl_service.is_allowed(user_id, acl_path, "write"):
            self._emit_trace("acl_denied", user_id=user_id, resource_path=acl_path, metadata={"action": "patch"})
            raise ValueError(f"write access denied for `{acl_path}`")
        result = self._file_service.patch(path, content, mode=mode)
        self._emit_trace("file_patch", user_id=user_id, resource_path=acl_path, metadata={"action": "patch", "mode": mode})
        return result
