from __future__ import annotations

import re
from typing import Any

import httpx

from app.core.config import settings
from app.services.capability_service import CapabilityService
from app.services.rag_service import RagService
from app.services.skill_executor_service import SkillExecutorService


class FindSkillsTool:
    tool_id = "find-skills"
    display_name = "Find Skills"
    description = "Search locally known skills and return a short ranked list."
    category = "discovery"

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
    description = "Search tenant-scoped knowledge in Zep with optional RAG scope filtering."
    category = "knowledge"

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
