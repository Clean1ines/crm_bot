from __future__ import annotations

from typing import Protocol

from src.contexts.knowledge_workbench.source_management.domain.entities.source_document import (
    SourceDocument,
)
from src.contexts.knowledge_workbench.source_management.domain.entities.source_unit import (
    SourceUnit,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_document_ref import (
    SourceDocumentRef,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_ref import (
    SourceUnitRef,
)


class SourceManagementRepositoryPort(Protocol):
    async def save_source_document(self, document: SourceDocument) -> None: ...

    async def load_source_document(
        self,
        document_ref: SourceDocumentRef,
    ) -> SourceDocument | None: ...

    async def save_source_units(
        self,
        units: tuple[SourceUnit, ...],
    ) -> None: ...

    async def list_source_units_for_document(
        self,
        document_ref: SourceDocumentRef,
    ) -> tuple[SourceUnit, ...]: ...

    async def load_source_unit(
        self,
        unit_ref: SourceUnitRef,
    ) -> SourceUnit | None: ...
