from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WorkKind:
    """Names the kind of work without leaking lifecycle or checkpoint semantics.

    Good values should be stable, lowercase, dotted identifiers owned by the
    calling bounded context.
    """

    value: str

    def __post_init__(self) -> None:
        value = self.value.strip() if self.value else ""
        if not value:
            raise ValueError("WorkKind.value must be non-empty")
        if " " in value:
            raise ValueError("WorkKind.value must not contain spaces")
        if value != value.lower():
            raise ValueError("WorkKind.value must be lowercase")
