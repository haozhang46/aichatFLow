from __future__ import annotations

from typing import Optional

from app.contracts.otie import IntentEnvelope, OtieRequestInput


class IntentService:
    def normalize(self, request: OtieRequestInput) -> IntentEnvelope:
        query = request.messages[0].content.strip()
        mode_hint = self._get_strategy(request)
        return IntentEnvelope(
            requestId=request.request_id,
            tenantId=request.tenant_id,
            sourceRequestType=request.request_type,
            userQuery=query,
            modeHint=mode_hint,
            executionMode=self._get_execution_mode(request, query),
            llmConfig=self._get_llm_config(request),
            metadata=request.metadata,
            constraints={
                "requestInputs": request.inputs,
                "messageCount": len(request.messages),
            },
        )

    def _get_strategy(self, request: OtieRequestInput) -> str:
        raw_strategy = request.inputs.get("strategy")
        if isinstance(raw_strategy, str) and raw_strategy in {"auto", "agent", "react", "workflow"}:
            return raw_strategy
        return "auto"

    def _get_execution_mode(self, request: OtieRequestInput, query: str) -> str:
        raw = request.inputs.get("executionMode")
        if isinstance(raw, str) and raw in {"auto_exec", "user_exec"}:
            return raw
        q = query.lower()
        if any(k in q for k in ["学习计划", "学习", "计划", "checklist", "清单", "todo", "roadmap"]):
            return "user_exec"
        return "auto_exec"

    def _get_llm_config(self, request: OtieRequestInput) -> Optional[dict[str, str]]:
        raw = request.inputs.get("llmConfig")
        if not isinstance(raw, dict):
            return None
        provider = str(raw.get("provider", "")).strip().lower()
        api_key = str(raw.get("apiKey", "")).strip()
        base_url = str(raw.get("baseUrl", "")).strip()
        model = str(raw.get("model", "")).strip()
        if provider != "deepseek" or not api_key:
            return None
        return {
            "apiKey": api_key,
            "baseUrl": base_url or "https://api.deepseek.com/v1",
            "model": model or "deepseek-chat",
        }
