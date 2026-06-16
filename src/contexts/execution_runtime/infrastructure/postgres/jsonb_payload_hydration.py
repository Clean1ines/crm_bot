from __future__ import annotations

import json
from collections.abc import Mapping


def hydrate_jsonb_object_payload(
    value: object,
    *,
    field_name: str,
) -> Mapping[str, object]:
    _require_non_empty_text(field_name, "field_name")

    if isinstance(value, Mapping):
        return dict(value)

    if isinstance(value, str):
        return _hydrate_json_text(value, field_name=field_name, source_type="str")

    if isinstance(value, (bytes, bytearray)):
        return _hydrate_json_text(
            bytes(value).decode("utf-8"),
            field_name=field_name,
            source_type=type(value).__name__,
        )

    raise TypeError(
        f"{field_name} must be JSON object Mapping; got {type(value).__name__}"
    )


def _hydrate_json_text(
    value: str,
    *,
    field_name: str,
    source_type: str,
) -> Mapping[str, object]:
    try:
        decoded: object = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"{field_name} must be JSON object Mapping; got invalid JSON {source_type}"
        ) from exc

    if not isinstance(decoded, Mapping):
        raise TypeError(
            f"{field_name} must be JSON object Mapping; got {source_type} "
            f"that decoded to {type(decoded).__name__}"
        )

    return dict(decoded)


def _require_non_empty_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty")
