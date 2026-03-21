from app.services.schema_validation import extract_json_value, validate_llm_text_against_schema


def test_extract_json_from_fence():
    text = """```json
{"a": 1}
```"""
    assert extract_json_value(text) == {"a": 1}


def test_validate_llm_text_against_schema_ok():
    schema = {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]}
    vr = validate_llm_text_against_schema('{"x": "hi"}', schema)
    assert vr.ok


def test_validate_llm_text_against_schema_fail():
    schema = {"type": "object", "properties": {"x": {"type": "number"}}, "required": ["x"]}
    vr = validate_llm_text_against_schema('{"x": "not-a-number"}', schema)
    assert not vr.ok
