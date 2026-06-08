from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ArtifactKind:
    """Stable caller-owned artifact kind.

    The artifact runtime stores the kind but does not interpret its business meaning.
    """

    value: str

    def __post_init__(self) -> None:
        value = self.value.strip() if self.value else ""
        if not value:
            raise ValueError("ArtifactKind.value must be non-empty")
        if " " in value:
            raise ValueError("ArtifactKind.value must not contain spaces")
        if value != value.lower():
            raise ValueError("ArtifactKind.value must be lowercase")
