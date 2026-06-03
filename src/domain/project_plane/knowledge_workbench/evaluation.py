from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .shared import (
    DocumentId,
    DomainInvariantError,
    JsonValue,
    ProjectId,
    RagEvalRunId,
    SurfaceId,
    require_project_id,
)


class RagEvalMode(StrEnum):
    PRODUCTION_EQUIVALENT = "production_equivalent"
    VECTOR_DEBUG = "vector_debug"


class RagEvalPurpose(StrEnum):
    QUALITY_CHECK = "quality_check"
    ENRICHMENT = "enrichment"


class RagEvalScope(StrEnum):
    DOCUMENT = "document"
    PROJECT = "project"
    SELECTED_SURFACES = "selected_surfaces"


class RagEvalRunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class RagEvalEnrichmentProposalType(StrEnum):
    ADD_VARIANT = "add_variant"
    IMPROVE_EMBEDDING_TEXT = "improve_embedding_text"
    SPLIT_SURFACE = "split_surface"
    MERGE_SURFACE = "merge_surface"
    ADD_EVIDENCE = "add_evidence"


class RagEvalEnrichmentProposalStatus(StrEnum):
    PROPOSED = "proposed"
    ACCEPTED_TO_CURATION = "accepted_to_curation"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class RagEvalRunRef:
    rag_eval_run_id: RagEvalRunId
    project_id: ProjectId
    scope: RagEvalScope
    mode: RagEvalMode
    purpose: RagEvalPurpose
    status: RagEvalRunStatus
    document_id: DocumentId | None = None
    selected_surface_ids: tuple[SurfaceId, ...] = ()

    def __post_init__(self) -> None:
        if not self.rag_eval_run_id:
            raise DomainInvariantError("rag_eval_run_id is required")
        require_project_id(self.project_id)
        if self.scope is RagEvalScope.DOCUMENT and self.document_id is None:
            raise DomainInvariantError("document-scope RAG eval requires document_id")
        if (
            self.scope is RagEvalScope.SELECTED_SURFACES
            and not self.selected_surface_ids
        ):
            raise DomainInvariantError(
                "selected-surfaces RAG eval requires selected_surface_ids"
            )


@dataclass(frozen=True, slots=True)
class RagEvalEnrichmentProposal:
    proposal_id: str
    rag_eval_run_id: RagEvalRunId
    project_id: ProjectId
    surface_id: SurfaceId
    proposal_type: RagEvalEnrichmentProposalType
    payload: JsonValue
    status: RagEvalEnrichmentProposalStatus

    def __post_init__(self) -> None:
        if not self.proposal_id:
            raise DomainInvariantError("proposal_id is required")
        if not self.rag_eval_run_id:
            raise DomainInvariantError("rag_eval_run_id is required")
        require_project_id(self.project_id)
        if not self.surface_id:
            raise DomainInvariantError("surface_id is required")


def rag_eval_enrichment_mutates_runtime(_: RagEvalEnrichmentProposal) -> bool:
    return False
