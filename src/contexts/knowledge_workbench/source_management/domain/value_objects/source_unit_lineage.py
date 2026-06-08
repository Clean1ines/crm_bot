from __future__ import annotations

from dataclasses import dataclass

from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_ref import (
    SourceUnitRef,
)


@dataclass(frozen=True, slots=True)
class SourceUnitLineage:
    parent_refs: tuple[SourceUnitRef, ...] = ()

    def __post_init__(self) -> None:
        copied_parent_refs = tuple(self.parent_refs)
        if len(set(copied_parent_refs)) != len(copied_parent_refs):
            raise ValueError(
                "SourceUnitLineage.parent_refs must not contain duplicates"
            )
        object.__setattr__(self, "parent_refs", copied_parent_refs)
