from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, TypeAlias


JsonScalar: TypeAlias = None | bool | int | float | str
JsonValue: TypeAlias = JsonScalar | tuple[JsonScalar, ...] | Mapping[str, JsonScalar]


@dataclass(frozen=True, slots=True)
class ArtifactPayload:
    """Opaque JSON-like payload.

    The artifact runtime stores payload shape but does not interpret its meaning.
    """

    value: Mapping[str, JsonValue]

    def __post_init__(self) -> None:
        if not isinstance(self.value, Mapping):
            raise ValueError("ArtifactPayload.value must be a mapping")
        object.__setattr__(self, "value", MappingProxyType(dict(self.value)))
