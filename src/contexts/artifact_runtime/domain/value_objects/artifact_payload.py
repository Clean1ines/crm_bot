from __future__ import annotations

from collections.abc import Mapping as MappingABC
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, TypeAlias


JsonScalar: TypeAlias = None | bool | int | float | str
JsonValue: TypeAlias = JsonScalar | tuple["JsonValue", ...] | Mapping[str, "JsonValue"]
JsonInputValue: TypeAlias = (
    JsonScalar
    | list["JsonInputValue"]
    | tuple["JsonInputValue", ...]
    | Mapping[str, "JsonInputValue"]
)


@dataclass(frozen=True, slots=True)
class ArtifactPayload:
    """Opaque recursively frozen JSON-like payload.

    The artifact runtime stores payload shape but does not interpret its meaning.
    """

    value: Mapping[str, JsonInputValue]

    def __post_init__(self) -> None:
        if not isinstance(self.value, MappingABC):
            raise ValueError("ArtifactPayload.value must be a mapping")

        frozen_mapping = self._freeze_json_mapping(self.value)
        object.__setattr__(self, "value", frozen_mapping)

    def _freeze_json_mapping(
        self,
        value: Mapping[str, JsonInputValue],
    ) -> Mapping[str, JsonValue]:
        frozen: dict[str, JsonValue] = {}

        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("ArtifactPayload object keys must be strings")
            frozen[key] = self._freeze_json_value(item)

        return MappingProxyType(frozen)

    def _freeze_json_value(self, value: JsonInputValue) -> JsonValue:
        if value is None or isinstance(value, (bool, int, float, str)):
            return value

        if isinstance(value, list):
            return tuple(self._freeze_json_value(item) for item in value)

        if isinstance(value, tuple):
            return tuple(self._freeze_json_value(item) for item in value)

        if isinstance(value, MappingABC):
            return self._freeze_json_mapping(value)

        raise ValueError("ArtifactPayload.value contains unsupported JSON value")
