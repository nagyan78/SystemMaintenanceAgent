import json
from collections.abc import Mapping
from typing import Any


def coerce_json_object(value: Mapping[str, Any] | str, *, field_name: str) -> dict[str, Any]:
    """Accept a tool-call object or a JSON-encoded object, never arbitrary JSON."""
    if isinstance(value, Mapping):
        return dict(value)
    if not isinstance(value, str):
        raise ValueError(f"{field_name} 必须是 JSON 对象。")
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{field_name} 不是有效 JSON 对象：{exc.msg}。") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"{field_name} 必须是 JSON 对象，不能是数组或标量。")
    return parsed
