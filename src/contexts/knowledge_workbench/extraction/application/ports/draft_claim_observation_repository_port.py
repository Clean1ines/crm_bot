from __future__ import annotations

from typing import Protocol

from src.contexts.knowledge_workbench.extraction.domain.entities.draft_claim_observation import (
    DraftClaimObservation,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_document_ref import (
    SourceDocumentRef,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_ref import (
    SourceUnitRef,
)


class DraftClaimObservationRepositoryPort(Protocol):
    def save_many(
        self,
        observations: tuple[DraftClaimObservation, ...],
    ) -> None: ...

    def list_by_source_unit(
        self,
        source_unit_ref: SourceUnitRef,
    ) -> tuple[DraftClaimObservation, ...]: ...

    def list_by_document(
        self,
        document_ref: SourceDocumentRef,
    ) -> tuple[DraftClaimObservation, ...]: ...
