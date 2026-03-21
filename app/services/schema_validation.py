"""Optional JSON Schema validation for step LLM outputs (TASK-P1-02)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Optional

try:
    from jsonschema import Draft7Validator
    from jsonschema.exceptions import ValidationError
except ImportError:  # pragma: no cover
    Draft7Validator = None  # type: ignore[misc, assignment]
    ValidationError = Exception  # type: ignore[misc, assignment]


@dataclass
class SchemaValidationResult:
    ok: bool
    error: Optional[str] = None
    parsed: Any = None


def extract_json_value(text: str) -> Any:
    """
    Parse first JSON object/array from LLM output (strip markdown fences).
    """
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z0-9]*\s*", "", raw)
        raw = re.sub(r"\s*```\s*$", "", raw).strip()
    raw = raw.strip()
    if not raw:
        raise ValueError("empty output")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    start_obj = raw.find("{")
    start_arr = raw.find("[")
    if start_obj < 0 and start_arr < 0:
        raise ValueError("no json object or array found")
    if start_arr >= 0 and (start_obj < 0 or start_arr < start_obj):
        end = raw.rfind("]")
        if end > start_arr:
            return json.loads(raw[start_arr : end + 1])
    if start_obj >= 0:
        end = raw.rfind("}")
        if end > start_obj:
            return json.loads(raw[start_obj : end + 1])
    raise ValueError("could not parse json")


def validate_against_schema(instance: Any, schema: dict[str, Any]) -> SchemaValidationResult:
    if Draft7Validator is None:
        return SchemaValidationResult(ok=False, error="jsonschema package not installed")
    try:
        Draft7Validator(schema).validate(instance)
    except ValidationError as exc:  # type: ignore[misc]
        return SchemaValidationResult(ok=False, error=str(exc.message), parsed=instance)
    except Exception as exc:  # pragma: no cover
        return SchemaValidationResult(ok=False, error=str(exc), parsed=instance)
    return SchemaValidationResult(ok=True, parsed=instance)


def validate_llm_text_against_schema(answer_text: str, schema: dict[str, Any]) -> SchemaValidationResult:
    try:
        parsed = extract_json_value(answer_text)
    except (ValueError, json.JSONDecodeError) as exc:
        return SchemaValidationResult(ok=False, error=f"json parse: {exc}")
    return validate_against_schema(parsed, schema)
