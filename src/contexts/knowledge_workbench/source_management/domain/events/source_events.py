from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_document_ref import (
    SourceDocumentRef,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_ref import (
    SourceUnitRef,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.split_reason import (
    SplitReason,
)


def _ensure_timezone_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class SourceDocumentCreated:
    document_ref: SourceDocumentRef
    occurred_at: datetime

    def __post_init__(self) -> None:
        _ensure_timezone_aware(self.occurred_at, "occurred_at")


@dataclass(frozen=True, slots=True)
class SourceUnitCreated:
    unit_ref: SourceUnitRef
    document_ref: SourceDocumentRef
    occurred_at: datetime

    def __post_init__(self) -> None:
        _ensure_timezone_aware(self.occurred_at, "occurred_at")


@dataclass(frozen=True, slots=True)
class SourceUnitSplit:
    parent_unit_ref: SourceUnitRef
    child_unit_refs: tuple[SourceUnitRef, ...]
    reason: SplitReason
    occurred_at: datetime

    def __post_init__(self) -> None:
        _ensure_timezone_aware(self.occurred_at, "occurred_at")
        child_refs = tuple(self.child_unit_refs)
        if not child_refs:
            raise ValueError("SourceUnitSplit.child_unit_refs must be non-empty")
        if len(set(child_refs)) != len(child_refs):
            raise ValueError(
                "SourceUnitSplit.child_unit_refs must not contain duplicates"
            )
        object.__setattr__(self, "child_unit_refs", child_refs)
