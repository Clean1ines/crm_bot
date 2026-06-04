from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from .shared import (
    ApplicationId,
    DocumentId,
    DomainInvariantError,
    ClaimObservationId,
    JsonValue,
    NodeRunId,
    ProcessingRunId,
    ProjectId,
    ProposalId,
    FactId,
    RegistryId,
    SectionId,
    SnapshotId,
    require_document_id,
    require_node_run_id,
    require_processing_run_id,
    require_project_id,
)


class ClaimObservationAction(StrEnum):
    NEW = "new"
    EXTENDS_EXISTING = "extends_existing"
    REFINES_EXISTING = "refines_existing"
    ADDS_EVIDENCE = "adds_evidence"
    CHILD_OF = "child_of"
    PARENT_OF = "parent_of"
    UMBRELLA_FOR = "umbrella_for"
    DUPLICATE_OF = "duplicate_of"
    OVERLAPS = "overlaps"


class ClaimObservationStatus(StrEnum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    ABSORBED = "absorbed"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class FactRegistryStatus(StrEnum):
    BUILDING = "building"
    PARTIALLY_BUILT = "partially_built"
    COMPLETED = "completed"
    INVALIDATED = "invalidated"
    DELETED = "deleted"


class CanonicalFactStatus(StrEnum):
    ACTIVE = "active"
    MERGED = "merged"
    REJECTED = "rejected"
    READY_FOR_SURFACE = "ready_for_surface"
    DELETED = "deleted"


class RegistryUpdateOperation(StrEnum):
    CREATE = "create"
    ADD_EVIDENCE = "add_evidence"
    EXTEND = "extend"
    REFINE = "refine"
    ADD_CHILD = "add_child"
    ADD_PARENT = "add_parent"
    MARK_DUPLICATE = "mark_duplicate"
    MARK_OVERLAP = "mark_overlap"
    SKIP_ROLE_LABEL = "skip_role_label"
    ABSORB_ROLE_LABEL = "absorb_role_label"
    REJECT = "reject"


class RegistryUpdateProposalStatus(StrEnum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    PARTIALLY_APPLIED = "partially_applied"
    SUPERSEDED_BY_DETERMINISTIC_RULE = "superseded_by_deterministic_rule"


class RegistryUpdateAppliedBy(StrEnum):
    DETERMINISTIC_CODE = "deterministic_code"
    LLM_ADVISORY = "llm_advisory"
    USER_CURATION = "user_curation"
    SYSTEM_RECOVERY = "system_recovery"


@dataclass(frozen=True, slots=True)
class ClaimObservationRecord:
    claim_observation_id: ClaimObservationId
    node_run_id: NodeRunId
    processing_run_id: ProcessingRunId
    project_id: ProjectId
    document_id: DocumentId
    section_id: SectionId
    action: ClaimObservationAction
    claim_local_ref: str
    title: str
    claim: str
    claim_kind: str
    answer: str
    short_answer: str
    claim_delta: str
    answer_scope: str
    retrieval_scope: str
    exclusion_scope: str
    variants: tuple[str, ...]
    evidence_quotes: tuple[str, ...]
    source_refs: tuple[str, ...]
    source_chunk_indexes: tuple[int, ...]
    confidence: float
    reason: str
    status: ClaimObservationStatus
    target_fact_id: FactId | None = None

    def __post_init__(self) -> None:
        if not self.claim_observation_id:
            raise DomainInvariantError("claim_observation_id is required")
        require_node_run_id(self.node_run_id)
        require_processing_run_id(self.processing_run_id)
        require_project_id(self.project_id)
        require_document_id(self.document_id)
        if not self.section_id:
            raise DomainInvariantError(
                "ClaimObservationRecord must reference section_id"
            )
        if self.action is not ClaimObservationAction.ADDS_EVIDENCE and not self.claim:
            raise DomainInvariantError("claim observation must have claim")
        if self.confidence < 0 or self.confidence > 1:
            raise DomainInvariantError("confidence must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class DeterministicDedupResult:
    dedup_result_id: str
    node_run_id: NodeRunId
    processing_run_id: ProcessingRunId
    project_id: ProjectId
    document_id: DocumentId
    input_claim_input_refs: tuple[ClaimObservationId, ...]
    exact_question_duplicate_groups: tuple[tuple[ClaimObservationId, ...], ...]
    exact_answer_duplicate_groups: tuple[tuple[ClaimObservationId, ...], ...]
    absorbed_role_labels: tuple[str, ...]
    kept_separate: tuple[ClaimObservationId, ...]
    warnings: tuple[str, ...]
    section_id: SectionId | None = None

    def __post_init__(self) -> None:
        if not self.dedup_result_id:
            raise DomainInvariantError("dedup_result_id is required")
        require_node_run_id(self.node_run_id)
        require_processing_run_id(self.processing_run_id)
        require_project_id(self.project_id)
        require_document_id(self.document_id)


@dataclass(frozen=True, slots=True)
class FactRegistry:
    registry_id: RegistryId
    project_id: ProjectId
    document_id: DocumentId
    processing_run_id: ProcessingRunId
    status: FactRegistryStatus
    version: int
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.registry_id:
            raise DomainInvariantError("registry_id is required")
        require_project_id(self.project_id)
        require_document_id(self.document_id)
        require_processing_run_id(self.processing_run_id)
        if self.version < 1:
            raise DomainInvariantError("registry version must be positive")


@dataclass(frozen=True, slots=True)
class CanonicalFact:
    fact_id: FactId
    registry_id: RegistryId
    project_id: ProjectId
    document_id: DocumentId
    processing_run_id: ProcessingRunId
    fact_key: str
    claim: str
    question_variants: tuple[str, ...]
    claim_kind: str
    answer: str
    short_answer: str
    answer_scope: str
    retrieval_scope: str
    exclusion_scope: str
    evidence_quotes: tuple[str, ...]
    source_refs: tuple[str, ...]
    source_section_ids: tuple[SectionId, ...]
    source_chunk_indexes: tuple[int, ...]
    parent_fact_ids: tuple[FactId, ...]
    child_fact_ids: tuple[FactId, ...]
    duplicate_fact_ids: tuple[FactId, ...]
    overlap_fact_ids: tuple[FactId, ...]
    role_label_metadata: dict[str, JsonValue]
    status: CanonicalFactStatus

    def __post_init__(self) -> None:
        if not self.fact_id:
            raise DomainInvariantError("fact_id is required")
        if not self.registry_id:
            raise DomainInvariantError("registry_id is required")
        require_project_id(self.project_id)
        require_document_id(self.document_id)
        require_processing_run_id(self.processing_run_id)
        if self.status is CanonicalFactStatus.ACTIVE and not self.claim:
            raise DomainInvariantError("active canonical fact must have claim")


@dataclass(frozen=True, slots=True)
class RegistryUpdateProposal:
    proposal_id: ProposalId
    node_run_id: NodeRunId
    processing_run_id: ProcessingRunId
    project_id: ProjectId
    document_id: DocumentId
    section_id: SectionId
    operation: RegistryUpdateOperation
    payload: JsonValue
    confidence: float
    reason: str
    status: RegistryUpdateProposalStatus
    created_at: datetime | None = None
    target_fact_id: FactId | None = None
    source_claim_observation_id: ClaimObservationId | None = None

    def __post_init__(self) -> None:
        if not self.proposal_id:
            raise DomainInvariantError("proposal_id is required")
        require_node_run_id(self.node_run_id)
        require_processing_run_id(self.processing_run_id)
        require_project_id(self.project_id)
        require_document_id(self.document_id)
        if not self.section_id:
            raise DomainInvariantError(
                "RegistryUpdateProposal must reference section_id"
            )
        if self.confidence < 0 or self.confidence > 1:
            raise DomainInvariantError("confidence must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class RegistryUpdateApplication:
    application_id: ApplicationId
    processing_run_id: ProcessingRunId
    project_id: ProjectId
    document_id: DocumentId
    operation: RegistryUpdateOperation
    applied_by: RegistryUpdateAppliedBy
    target_fact_id: FactId
    after_snapshot_id: SnapshotId
    payload: JsonValue
    applied_at: datetime | None = None
    section_id: SectionId | None = None
    proposal_id: ProposalId | None = None
    before_snapshot_id: SnapshotId | None = None

    def __post_init__(self) -> None:
        if not self.application_id:
            raise DomainInvariantError("application_id is required")
        require_processing_run_id(self.processing_run_id)
        require_project_id(self.project_id)
        require_document_id(self.document_id)
        if not self.target_fact_id:
            raise DomainInvariantError("target_fact_id is required")
        if not self.after_snapshot_id:
            raise DomainInvariantError("after_snapshot_id is required")


@dataclass(frozen=True, slots=True)
class RegistrySnapshot:
    snapshot_id: SnapshotId
    registry_id: RegistryId
    processing_run_id: ProcessingRunId
    project_id: ProjectId
    document_id: DocumentId
    after_node_run_id: NodeRunId
    sequence_number: int
    entries_payload: JsonValue
    relations_payload: JsonValue
    entry_count: int
    relation_count: int
    claim_observation_count: int
    update_count: int
    created_at: datetime | None = None
    after_section_id: SectionId | None = None

    def __post_init__(self) -> None:
        if not self.snapshot_id:
            raise DomainInvariantError("snapshot_id is required")
        if not self.registry_id:
            raise DomainInvariantError("registry_id is required")
        require_processing_run_id(self.processing_run_id)
        require_project_id(self.project_id)
        require_document_id(self.document_id)
        require_node_run_id(self.after_node_run_id)
        if self.sequence_number < 1:
            raise DomainInvariantError("snapshot sequence_number must be positive")


def proposal_mutates_registry(_: RegistryUpdateProposal) -> bool:
    return False


def apply_registry_update(
    *,
    entry: CanonicalFact,
    application: RegistryUpdateApplication,
    claim: str | None = None,
    answer: str | None = None,
    short_answer: str | None = None,
    added_variants: tuple[str, ...] = (),
    added_evidence_quotes: tuple[str, ...] = (),
    added_source_refs: tuple[str, ...] = (),
    status: CanonicalFactStatus | None = None,
) -> CanonicalFact:
    if application.target_fact_id != entry.fact_id:
        raise DomainInvariantError("application target does not match canonical fact")
    return replace(
        entry,
        claim=claim if claim is not None else entry.claim,
        answer=answer if answer is not None else entry.answer,
        short_answer=short_answer if short_answer is not None else entry.short_answer,
        question_variants=entry.question_variants + added_variants,
        evidence_quotes=entry.evidence_quotes + added_evidence_quotes,
        source_refs=entry.source_refs + added_source_refs,
        status=status if status is not None else entry.status,
    )


def ensure_resume_uses_registry_snapshot(snapshot: RegistrySnapshot) -> None:
    if snapshot.entry_count < 0 or snapshot.update_count < 0:
        raise DomainInvariantError("invalid registry snapshot counters")
