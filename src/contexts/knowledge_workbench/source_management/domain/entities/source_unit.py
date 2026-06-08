from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.contexts.knowledge_workbench.source_management.domain.value_objects.heading_path import (
    HeadingPath,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_document_ref import (
    SourceDocumentRef,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_kind import (
    SourceUnitKind,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_lineage import (
    SourceUnitLineage,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_ref import (
    SourceUnitRef,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_text import (
    SourceUnitText,
)


@dataclass(frozen=True, slots=True)
class SourceUnit:
    unit_ref: SourceUnitRef
    document_ref: SourceDocumentRef
    unit_kind: SourceUnitKind
    text: SourceUnitText
    heading_path: HeadingPath
    lineage: SourceUnitLineage
    ordinal: int
    created_at: datetime

    def __post_init__(self) -> None:
        if self.ordinal < 0:
            raise ValueError("SourceUnit.ordinal must be >= 0")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("SourceUnit.created_at must be timezone-aware")
