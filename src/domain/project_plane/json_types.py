from __future__ import annotations

import json

JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | dict[str, "JsonValue"] | list["JsonValue"]
JsonObject = dict[str, JsonValue]


def json_value_from_unknown(value: object) -> JsonValue:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, list):
        return [json_value_from_unknown(item) for item in value]

    if isinstance(value, dict):
        return {str(key): json_value_from_unknown(item) for key, item in value.items()}

    return str(value)


def json_object_from_unknown(value: object) -> JsonObject:
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return json_object_from_unknown(decoded)

    if not isinstance(value, dict):
        return {}

    return {str(key): json_value_from_unknown(item) for key, item in value.items()}
