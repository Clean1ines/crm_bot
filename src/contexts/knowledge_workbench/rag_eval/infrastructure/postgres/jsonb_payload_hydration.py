from __future__ import annotations

import json
from collections.abc import Sequence


def hydrate_jsonb_text_array_payload(
    value: object,
    *,
    field_name: str,
) -> tuple[str, ...]:
    _require_non_empty_text(field_name, "field_name")

    if value is None:
        return ()

    raw_value = value
    if isinstance(value, str):
        raw_value = _load_json_text(value, field_name=field_name, source_type="str")
    elif isinstance(value, (bytes, bytearray)):
        raw_value = _load_json_text(
            bytes(value).decode("utf-8"),
            field_name=field_name,
            source_type=type(value).__name__,
        )

    if not isinstance(raw_value, Sequence) or isinstance(
        raw_value,
        (str, bytes, bytearray),
    ):
        raise TypeError(
            f"{field_name} must be JSON text array; got {type(raw_value).__name__}"
        )

    return tuple(
        item.strip() for item in raw_value if isinstance(item, str) and item.strip()
    )


def _load_json_text(
    value: str,
    *,
    field_name: str,
    source_type: str,
) -> object:
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"{field_name} must be JSON text array; got invalid JSON {source_type}"
        ) from exc


def _require_non_empty_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty")
