from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TypeAlias

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | Sequence["JsonValue"] | Mapping[str, "JsonValue"]
JsonObject: TypeAlias = Mapping[str, JsonValue]

ProviderId: TypeAlias = str
ModelName: TypeAlias = str
ApiKeySlot: TypeAlias = str
OperationName: TypeAlias = str
RouteChainId: TypeAlias = str


class LlmRoutingInvariantError(ValueError):
    pass


def require_non_empty(value: str, *, field_name: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise LlmRoutingInvariantError(f"{field_name} is required")
    return stripped


def require_non_negative_int(value: int, *, field_name: str) -> int:
    if value < 0:
        raise LlmRoutingInvariantError(f"{field_name} must be non-negative")
    return value


def require_positive_int(value: int, *, field_name: str) -> int:
    if value <= 0:
        raise LlmRoutingInvariantError(f"{field_name} must be positive")
    return value
