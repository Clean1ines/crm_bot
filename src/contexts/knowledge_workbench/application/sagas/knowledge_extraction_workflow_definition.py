from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_saga_state import (
    KnowledgeExtractionPhaseKey,
)


class KnowledgeExtractionCanonicalPhase(StrEnum):
    WORKFLOW_STARTED = "WORKFLOW_STARTED"
    SOURCE_INGESTION = "SOURCE_INGESTION"
    CLAIM_BUILDER_WORK_SCHEDULING = "CLAIM_BUILDER_WORK_SCHEDULING"
    CLAIM_BUILDER_SECTION_EXTRACTION = "CLAIM_BUILDER_SECTION_EXTRACTION"
    DRAFT_CLAIM_EMBEDDING = "DRAFT_CLAIM_EMBEDDING"
    DRAFT_CLAIM_CLUSTERING = "DRAFT_CLAIM_CLUSTERING"
    CLUSTER_PREVIEW_READY = "CLUSTER_PREVIEW_READY"


class KnowledgeExtractionCanonicalCommandType(StrEnum):
    START_KNOWLEDGE_EXTRACTION_WORKFLOW = "StartKnowledgeExtractionWorkflow"
    INGEST_SOURCE_DOCUMENT = "IngestSourceDocument"
    SCHEDULE_CLAIM_BUILDER_SECTION_WORK = "ScheduleClaimBuilderSectionWork"
    PREPARE_CLAIM_BUILDER_DISPATCH_BATCH = "PrepareClaimBuilderDispatchBatch"
    EXECUTE_CLAIM_BUILDER_SECTION = "ExecuteClaimBuilderSection"
    RECONCILE_CLAIM_BUILDER_PROGRESS = "ReconcileClaimBuilderProgress"
    GENERATE_DRAFT_CLAIM_EMBEDDINGS = "GenerateDraftClaimEmbeddings"
    CLUSTER_DRAFT_CLAIMS = "ClusterDraftClaims"
    BUILD_CLUSTER_PREVIEW = "BuildClusterPreview"
    PAUSE_FOR_CLUSTER_CONTRACT_REVIEW = "PauseForClusterContractReview"


class KnowledgeExtractionCanonicalEventType(StrEnum):
    KNOWLEDGE_EXTRACTION_WORKFLOW_STARTED = "KnowledgeExtractionWorkflowStarted"
    SOURCE_DOCUMENT_PERSISTED = "SourceDocumentPersisted"
    SOURCE_UNITS_CREATED = "SourceUnitsCreated"
    CLAIM_BUILDER_SECTION_WORK_SCHEDULED = "ClaimBuilderSectionWorkScheduled"
    CLAIM_BUILDER_DISPATCH_BATCH_PREPARED = "ClaimBuilderDispatchBatchPrepared"
    CLAIM_BUILDER_SECTION_EXTRACTION_STARTED = "ClaimBuilderSectionExtractionStarted"
    CLAIM_BUILDER_SECTION_EXTRACTED = "ClaimBuilderSectionExtracted"
    CLAIM_BUILDER_SECTION_EXTRACTION_DEFERRED = "ClaimBuilderSectionExtractionDeferred"
    CLAIM_BUILDER_SECTION_EXTRACTION_RETRYABLE_FAILED = (
        "ClaimBuilderSectionExtractionRetryableFailed"
    )
    CLAIM_BUILDER_SECTION_EXTRACTION_TERMINAL_FAILED = (
        "ClaimBuilderSectionExtractionTerminalFailed"
    )
    CLAIM_BUILDER_SECTION_SPLIT_REQUIRED = "ClaimBuilderSectionSplitRequired"
    LLM_PROVIDER_CAPACITY_OBSERVED = "LlmProviderCapacityObserved"
    CLAIM_BUILDER_ALL_SECTIONS_EXTRACTED = "ClaimBuilderAllSectionsExtracted"
    DRAFT_CLAIM_EMBEDDING_BATCH_COMPLETED = "DraftClaimEmbeddingBatchCompleted"
    DRAFT_CLAIM_EMBEDDINGS_GENERATED = "DraftClaimEmbeddingsGenerated"
    DRAFT_CLAIM_CLUSTERS_BUILT = "DraftClaimClustersBuilt"
    CLUSTER_PREVIEW_READY = "ClusterPreviewReady"
    CLUSTER_CONTRACT_REVIEW_REQUIRED = "ClusterContractReviewRequired"


class KnowledgeExtractionReadModelName(StrEnum):
    PROGRESS_SNAPSHOT = "progress_snapshot"
    ACTIVE_ATTEMPTS = "active_attempts"
    RECENT_CLAIMS = "recent_claims"
    TIMELINE = "timeline"
    CAPACITY_STATUS = "capacity_status"
    CLUSTER_PREVIEW = "cluster_preview"


class KnowledgeExtractionRecoveryScope(StrEnum):
    WORKFLOW = "workflow"
    PHASE = "phase"
    SOURCE_UNIT = "source_unit"
    WORK_ITEM_ATTEMPT = "work_item_attempt"
    CLAIM_BUILDER_SECTION = "claim_builder_section"
    EMBEDDING_BATCH = "embedding_batch"
    CLUSTER_BUILD = "cluster_build"
    CLUSTER_PREVIEW = "cluster_preview"


def _require_non_empty(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


@dataclass(frozen=True, slots=True)
class KnowledgeExtractionOperationContract:
    operation_key: str
    phase: KnowledgeExtractionCanonicalPhase
    command_type: KnowledgeExtractionCanonicalCommandType
    owner_contexts: tuple[str, ...]
    unit_of_work_name: str
    idempotency_key_template: str
    success_event_type: KnowledgeExtractionCanonicalEventType | None = None
    failure_event_types: tuple[KnowledgeExtractionCanonicalEventType, ...] = ()
    intermediate_event_types: tuple[KnowledgeExtractionCanonicalEventType, ...] = ()
    next_command_types: tuple[KnowledgeExtractionCanonicalCommandType, ...] = ()
    affected_read_models: tuple[KnowledgeExtractionReadModelName, ...] = ()
    recovery_scopes: tuple[KnowledgeExtractionRecoveryScope, ...] = ()
    frontend_visibility: bool = False

    def __post_init__(self) -> None:
        _require_non_empty(self.operation_key, "operation_key")
        _require_non_empty(self.unit_of_work_name, "unit_of_work_name")
        _require_non_empty(self.idempotency_key_template, "idempotency_key_template")
        if not self.owner_contexts:
            raise ValueError("owner_contexts must be non-empty")
        for owner_context in self.owner_contexts:
            _require_non_empty(owner_context, "owner_contexts")


@dataclass(frozen=True, slots=True)
class KnowledgeExtractionWorkflowContract:
    operations: tuple[KnowledgeExtractionOperationContract, ...]
    terminal_phase: KnowledgeExtractionCanonicalPhase

    def __post_init__(self) -> None:
        if not self.operations:
            raise ValueError("operations must be non-empty")

        operation_keys = tuple(operation.operation_key for operation in self.operations)
        if len(operation_keys) != len(set(operation_keys)):
            raise ValueError("operation keys must be unique")

        command_types = tuple(operation.command_type for operation in self.operations)
        if len(command_types) != len(set(command_types)):
            raise ValueError("primary command types must be unique")


@dataclass(frozen=True, slots=True)
class KnowledgeExtractionLegacyPhaseMapping:
    legacy_phase_key: str
    canonical_phase: KnowledgeExtractionCanonicalPhase
    migration_status: str
    replacement_reason: str

    def __post_init__(self) -> None:
        _require_non_empty(self.legacy_phase_key, "legacy_phase_key")
        _require_non_empty(self.migration_status, "migration_status")
        _require_non_empty(self.replacement_reason, "replacement_reason")


DEFAULT_KNOWLEDGE_EXTRACTION_WORKFLOW_CONTRACT = KnowledgeExtractionWorkflowContract(
    terminal_phase=KnowledgeExtractionCanonicalPhase.CLUSTER_PREVIEW_READY,
    operations=(
        KnowledgeExtractionOperationContract(
            operation_key="start_knowledge_extraction_workflow",
            phase=KnowledgeExtractionCanonicalPhase.WORKFLOW_STARTED,
            command_type=(
                KnowledgeExtractionCanonicalCommandType.START_KNOWLEDGE_EXTRACTION_WORKFLOW
            ),
            owner_contexts=(
                "knowledge_workbench",
                "workflow_runtime",
            ),
            unit_of_work_name="KnowledgeExtractionWorkflowStartUnitOfWork",
            idempotency_key_template="knowledge-extraction-start:{workflow_run_id}",
            success_event_type=(
                KnowledgeExtractionCanonicalEventType.KNOWLEDGE_EXTRACTION_WORKFLOW_STARTED
            ),
            next_command_types=(
                KnowledgeExtractionCanonicalCommandType.INGEST_SOURCE_DOCUMENT,
            ),
            affected_read_models=(
                KnowledgeExtractionReadModelName.PROGRESS_SNAPSHOT,
                KnowledgeExtractionReadModelName.TIMELINE,
            ),
            recovery_scopes=(KnowledgeExtractionRecoveryScope.WORKFLOW,),
            frontend_visibility=True,
        ),
        KnowledgeExtractionOperationContract(
            operation_key="ingest_source_document",
            phase=KnowledgeExtractionCanonicalPhase.SOURCE_INGESTION,
            command_type=KnowledgeExtractionCanonicalCommandType.INGEST_SOURCE_DOCUMENT,
            owner_contexts=(
                "knowledge_workbench",
                "source_management",
            ),
            unit_of_work_name="KnowledgeExtractionSourceIngestionUnitOfWork",
            idempotency_key_template="source-ingestion:{workflow_run_id}",
            success_event_type=KnowledgeExtractionCanonicalEventType.SOURCE_UNITS_CREATED,
            intermediate_event_types=(
                KnowledgeExtractionCanonicalEventType.SOURCE_DOCUMENT_PERSISTED,
            ),
            failure_event_types=(),
            next_command_types=(
                KnowledgeExtractionCanonicalCommandType.SCHEDULE_CLAIM_BUILDER_SECTION_WORK,
            ),
            affected_read_models=(
                KnowledgeExtractionReadModelName.PROGRESS_SNAPSHOT,
                KnowledgeExtractionReadModelName.TIMELINE,
            ),
            recovery_scopes=(
                KnowledgeExtractionRecoveryScope.WORKFLOW,
                KnowledgeExtractionRecoveryScope.PHASE,
            ),
            frontend_visibility=True,
        ),
        KnowledgeExtractionOperationContract(
            operation_key="schedule_claim_builder_section_work",
            phase=KnowledgeExtractionCanonicalPhase.CLAIM_BUILDER_WORK_SCHEDULING,
            command_type=(
                KnowledgeExtractionCanonicalCommandType.SCHEDULE_CLAIM_BUILDER_SECTION_WORK
            ),
            owner_contexts=(
                "knowledge_workbench",
                "execution_runtime",
            ),
            unit_of_work_name="ClaimBuilderSectionWorkSchedulingUnitOfWork",
            idempotency_key_template="claim-builder-section-work:{workflow_run_id}",
            success_event_type=(
                KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SECTION_WORK_SCHEDULED
            ),
            next_command_types=(
                KnowledgeExtractionCanonicalCommandType.PREPARE_CLAIM_BUILDER_DISPATCH_BATCH,
            ),
            affected_read_models=(
                KnowledgeExtractionReadModelName.PROGRESS_SNAPSHOT,
                KnowledgeExtractionReadModelName.TIMELINE,
            ),
            recovery_scopes=(
                KnowledgeExtractionRecoveryScope.PHASE,
                KnowledgeExtractionRecoveryScope.SOURCE_UNIT,
            ),
            frontend_visibility=True,
        ),
        KnowledgeExtractionOperationContract(
            operation_key="prepare_claim_builder_dispatch_batch",
            phase=KnowledgeExtractionCanonicalPhase.CLAIM_BUILDER_SECTION_EXTRACTION,
            command_type=(
                KnowledgeExtractionCanonicalCommandType.PREPARE_CLAIM_BUILDER_DISPATCH_BATCH
            ),
            owner_contexts=(
                "execution_runtime",
                "llm_runtime",
                "capacity_runtime",
            ),
            unit_of_work_name="ClaimBuilderDispatchBatchPreparationUnitOfWork",
            idempotency_key_template="claim-builder-dispatch-batch:{work_kind}:{worker_ref}",
            success_event_type=(
                KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_DISPATCH_BATCH_PREPARED
            ),
            next_command_types=(
                KnowledgeExtractionCanonicalCommandType.EXECUTE_CLAIM_BUILDER_SECTION,
            ),
            affected_read_models=(
                KnowledgeExtractionReadModelName.ACTIVE_ATTEMPTS,
                KnowledgeExtractionReadModelName.CAPACITY_STATUS,
                KnowledgeExtractionReadModelName.TIMELINE,
            ),
            recovery_scopes=(
                KnowledgeExtractionRecoveryScope.WORK_ITEM_ATTEMPT,
                KnowledgeExtractionRecoveryScope.CLAIM_BUILDER_SECTION,
            ),
            frontend_visibility=True,
        ),
        KnowledgeExtractionOperationContract(
            operation_key="execute_claim_builder_section",
            phase=KnowledgeExtractionCanonicalPhase.CLAIM_BUILDER_SECTION_EXTRACTION,
            command_type=KnowledgeExtractionCanonicalCommandType.EXECUTE_CLAIM_BUILDER_SECTION,
            owner_contexts=(
                "knowledge_workbench",
                "execution_runtime",
                "llm_runtime",
                "capacity_runtime",
                "artifact_runtime",
            ),
            unit_of_work_name="ClaimBuilderSectionExecutionUnitOfWork",
            idempotency_key_template="claim-builder-section:{work_item_attempt_id}",
            success_event_type=(
                KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SECTION_EXTRACTED
            ),
            failure_event_types=(
                KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SECTION_EXTRACTION_DEFERRED,
                KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SECTION_EXTRACTION_RETRYABLE_FAILED,
                KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SECTION_EXTRACTION_TERMINAL_FAILED,
                KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SECTION_SPLIT_REQUIRED,
            ),
            intermediate_event_types=(
                KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SECTION_EXTRACTION_STARTED,
                KnowledgeExtractionCanonicalEventType.LLM_PROVIDER_CAPACITY_OBSERVED,
            ),
            next_command_types=(
                KnowledgeExtractionCanonicalCommandType.RECONCILE_CLAIM_BUILDER_PROGRESS,
            ),
            affected_read_models=(
                KnowledgeExtractionReadModelName.PROGRESS_SNAPSHOT,
                KnowledgeExtractionReadModelName.ACTIVE_ATTEMPTS,
                KnowledgeExtractionReadModelName.RECENT_CLAIMS,
                KnowledgeExtractionReadModelName.TIMELINE,
                KnowledgeExtractionReadModelName.CAPACITY_STATUS,
            ),
            recovery_scopes=(
                KnowledgeExtractionRecoveryScope.SOURCE_UNIT,
                KnowledgeExtractionRecoveryScope.WORK_ITEM_ATTEMPT,
                KnowledgeExtractionRecoveryScope.CLAIM_BUILDER_SECTION,
            ),
            frontend_visibility=True,
        ),
        KnowledgeExtractionOperationContract(
            operation_key="reconcile_claim_builder_progress",
            phase=KnowledgeExtractionCanonicalPhase.CLAIM_BUILDER_SECTION_EXTRACTION,
            command_type=(
                KnowledgeExtractionCanonicalCommandType.RECONCILE_CLAIM_BUILDER_PROGRESS
            ),
            owner_contexts=(
                "knowledge_workbench",
                "execution_runtime",
            ),
            unit_of_work_name="ClaimBuilderProgressReconciliationUnitOfWork",
            idempotency_key_template="claim-builder-progress:{workflow_run_id}",
            success_event_type=(
                KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_ALL_SECTIONS_EXTRACTED
            ),
            next_command_types=(
                KnowledgeExtractionCanonicalCommandType.GENERATE_DRAFT_CLAIM_EMBEDDINGS,
            ),
            affected_read_models=(
                KnowledgeExtractionReadModelName.PROGRESS_SNAPSHOT,
                KnowledgeExtractionReadModelName.ACTIVE_ATTEMPTS,
                KnowledgeExtractionReadModelName.TIMELINE,
            ),
            recovery_scopes=(
                KnowledgeExtractionRecoveryScope.PHASE,
                KnowledgeExtractionRecoveryScope.CLAIM_BUILDER_SECTION,
            ),
            frontend_visibility=True,
        ),
        KnowledgeExtractionOperationContract(
            operation_key="generate_draft_claim_embeddings",
            phase=KnowledgeExtractionCanonicalPhase.DRAFT_CLAIM_EMBEDDING,
            command_type=(
                KnowledgeExtractionCanonicalCommandType.GENERATE_DRAFT_CLAIM_EMBEDDINGS
            ),
            owner_contexts=(
                "knowledge_workbench",
                "embedding_runtime",
            ),
            unit_of_work_name="DraftClaimEmbeddingGenerationUnitOfWork",
            idempotency_key_template="draft-claim-embeddings:{workflow_run_id}:{batch_ref}",
            success_event_type=(
                KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_EMBEDDINGS_GENERATED
            ),
            intermediate_event_types=(
                KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_EMBEDDING_BATCH_COMPLETED,
            ),
            failure_event_types=(),
            next_command_types=(
                KnowledgeExtractionCanonicalCommandType.CLUSTER_DRAFT_CLAIMS,
            ),
            affected_read_models=(
                KnowledgeExtractionReadModelName.PROGRESS_SNAPSHOT,
                KnowledgeExtractionReadModelName.RECENT_CLAIMS,
                KnowledgeExtractionReadModelName.TIMELINE,
            ),
            recovery_scopes=(KnowledgeExtractionRecoveryScope.EMBEDDING_BATCH,),
            frontend_visibility=True,
        ),
        KnowledgeExtractionOperationContract(
            operation_key="cluster_draft_claims",
            phase=KnowledgeExtractionCanonicalPhase.DRAFT_CLAIM_CLUSTERING,
            command_type=KnowledgeExtractionCanonicalCommandType.CLUSTER_DRAFT_CLAIMS,
            owner_contexts=(
                "knowledge_workbench",
                "embedding_runtime",
            ),
            unit_of_work_name="DraftClaimClusteringUnitOfWork",
            idempotency_key_template="draft-claim-clusters:{workflow_run_id}",
            success_event_type=KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_CLUSTERS_BUILT,
            next_command_types=(
                KnowledgeExtractionCanonicalCommandType.BUILD_CLUSTER_PREVIEW,
            ),
            affected_read_models=(
                KnowledgeExtractionReadModelName.PROGRESS_SNAPSHOT,
                KnowledgeExtractionReadModelName.TIMELINE,
            ),
            recovery_scopes=(KnowledgeExtractionRecoveryScope.CLUSTER_BUILD,),
            frontend_visibility=True,
        ),
        KnowledgeExtractionOperationContract(
            operation_key="build_cluster_preview",
            phase=KnowledgeExtractionCanonicalPhase.CLUSTER_PREVIEW_READY,
            command_type=KnowledgeExtractionCanonicalCommandType.BUILD_CLUSTER_PREVIEW,
            owner_contexts=("knowledge_workbench",),
            unit_of_work_name="ClusterPreviewBuildUnitOfWork",
            idempotency_key_template="cluster-preview:{workflow_run_id}",
            success_event_type=KnowledgeExtractionCanonicalEventType.CLUSTER_PREVIEW_READY,
            next_command_types=(
                KnowledgeExtractionCanonicalCommandType.PAUSE_FOR_CLUSTER_CONTRACT_REVIEW,
            ),
            affected_read_models=(
                KnowledgeExtractionReadModelName.PROGRESS_SNAPSHOT,
                KnowledgeExtractionReadModelName.TIMELINE,
                KnowledgeExtractionReadModelName.CLUSTER_PREVIEW,
            ),
            recovery_scopes=(KnowledgeExtractionRecoveryScope.CLUSTER_PREVIEW,),
            frontend_visibility=True,
        ),
        KnowledgeExtractionOperationContract(
            operation_key="pause_for_cluster_contract_review",
            phase=KnowledgeExtractionCanonicalPhase.CLUSTER_PREVIEW_READY,
            command_type=(
                KnowledgeExtractionCanonicalCommandType.PAUSE_FOR_CLUSTER_CONTRACT_REVIEW
            ),
            owner_contexts=("knowledge_workbench",),
            unit_of_work_name="ClusterContractReviewPauseUnitOfWork",
            idempotency_key_template="cluster-contract-review:{workflow_run_id}",
            success_event_type=(
                KnowledgeExtractionCanonicalEventType.CLUSTER_CONTRACT_REVIEW_REQUIRED
            ),
            next_command_types=(),
            affected_read_models=(
                KnowledgeExtractionReadModelName.PROGRESS_SNAPSHOT,
                KnowledgeExtractionReadModelName.TIMELINE,
                KnowledgeExtractionReadModelName.CLUSTER_PREVIEW,
            ),
            recovery_scopes=(
                KnowledgeExtractionRecoveryScope.WORKFLOW,
                KnowledgeExtractionRecoveryScope.CLUSTER_PREVIEW,
            ),
            frontend_visibility=True,
        ),
    ),
)


LEGACY_PHASE_MIGRATION_MAP = (
    KnowledgeExtractionLegacyPhaseMapping(
        legacy_phase_key=KnowledgeExtractionPhaseKey.DOCUMENT_ACCEPTED.value,
        canonical_phase=KnowledgeExtractionCanonicalPhase.SOURCE_INGESTION,
        migration_status="current_contract",
        replacement_reason="Source acceptance is normalized into source ingestion.",
    ),
    KnowledgeExtractionLegacyPhaseMapping(
        legacy_phase_key=KnowledgeExtractionPhaseKey.SOURCE_DOCUMENT_PERSISTED.value,
        canonical_phase=KnowledgeExtractionCanonicalPhase.SOURCE_INGESTION,
        migration_status="current_contract",
        replacement_reason="Document persistence is an ingestion intermediate event.",
    ),
    KnowledgeExtractionLegacyPhaseMapping(
        legacy_phase_key=KnowledgeExtractionPhaseKey.SOURCE_UNITS_CREATED.value,
        canonical_phase=KnowledgeExtractionCanonicalPhase.SOURCE_INGESTION,
        migration_status="current_contract",
        replacement_reason="Source unit creation completes source ingestion.",
    ),
    KnowledgeExtractionLegacyPhaseMapping(
        legacy_phase_key=KnowledgeExtractionPhaseKey.PROMPT_A_WORK_SCHEDULED.value,
        canonical_phase=KnowledgeExtractionCanonicalPhase.CLAIM_BUILDER_WORK_SCHEDULING,
        migration_status="current_contract",
        replacement_reason="Prompt A scheduling is renamed claim_builder section work scheduling.",
    ),
    KnowledgeExtractionLegacyPhaseMapping(
        legacy_phase_key=KnowledgeExtractionPhaseKey.PROMPT_A_WORK_COMPLETED.value,
        canonical_phase=KnowledgeExtractionCanonicalPhase.CLAIM_BUILDER_SECTION_EXTRACTION,
        migration_status="current_contract",
        replacement_reason="Prompt A completion is folded into claim_builder section extraction.",
    ),
    KnowledgeExtractionLegacyPhaseMapping(
        legacy_phase_key=KnowledgeExtractionPhaseKey.PROMPT_A_ARTIFACTS_APPLIED.value,
        canonical_phase=KnowledgeExtractionCanonicalPhase.CLAIM_BUILDER_SECTION_EXTRACTION,
        migration_status="current_contract",
        replacement_reason="Draft observation application is part of claim_builder section extraction.",
    ),
    KnowledgeExtractionLegacyPhaseMapping(
        legacy_phase_key=KnowledgeExtractionPhaseKey.DRAFT_EMBEDDINGS_BUILT.value,
        canonical_phase=KnowledgeExtractionCanonicalPhase.DRAFT_CLAIM_EMBEDDING,
        migration_status="current_contract",
        replacement_reason="Draft embeddings become draft claim embedding.",
    ),
    KnowledgeExtractionLegacyPhaseMapping(
        legacy_phase_key=KnowledgeExtractionPhaseKey.DRAFT_CLUSTERS_BUILT.value,
        canonical_phase=KnowledgeExtractionCanonicalPhase.DRAFT_CLAIM_CLUSTERING,
        migration_status="current_contract",
        replacement_reason="Draft clusters become draft claim clustering.",
    ),
    KnowledgeExtractionLegacyPhaseMapping(
        legacy_phase_key=KnowledgeExtractionPhaseKey.WAITING_FOR_REVIEW.value,
        canonical_phase=KnowledgeExtractionCanonicalPhase.CLUSTER_PREVIEW_READY,
        migration_status="current_contract",
        replacement_reason="Review waits at the cluster preview cutoff.",
    ),
    KnowledgeExtractionLegacyPhaseMapping(
        legacy_phase_key=KnowledgeExtractionPhaseKey.PROMPT_B_WORK_SCHEDULED.value,
        canonical_phase=KnowledgeExtractionCanonicalPhase.CLUSTER_PREVIEW_READY,
        migration_status="out_of_current_contract",
        replacement_reason="Prompt B starts after the cluster preview cutoff.",
    ),
    KnowledgeExtractionLegacyPhaseMapping(
        legacy_phase_key=KnowledgeExtractionPhaseKey.PROMPT_B_WORK_COMPLETED.value,
        canonical_phase=KnowledgeExtractionCanonicalPhase.CLUSTER_PREVIEW_READY,
        migration_status="out_of_current_contract",
        replacement_reason="Prompt B completion is after the cluster preview cutoff.",
    ),
    KnowledgeExtractionLegacyPhaseMapping(
        legacy_phase_key=KnowledgeExtractionPhaseKey.FINAL_KNOWLEDGE_PREPARED.value,
        canonical_phase=KnowledgeExtractionCanonicalPhase.CLUSTER_PREVIEW_READY,
        migration_status="out_of_current_contract",
        replacement_reason="Final knowledge preparation is outside this contract cutoff.",
    ),
    KnowledgeExtractionLegacyPhaseMapping(
        legacy_phase_key=KnowledgeExtractionPhaseKey.REVIEW_COMPLETED.value,
        canonical_phase=KnowledgeExtractionCanonicalPhase.CLUSTER_PREVIEW_READY,
        migration_status="out_of_current_contract",
        replacement_reason="Review completion is outside this contract cutoff.",
    ),
    KnowledgeExtractionLegacyPhaseMapping(
        legacy_phase_key=KnowledgeExtractionPhaseKey.PUBLISHED.value,
        canonical_phase=KnowledgeExtractionCanonicalPhase.CLUSTER_PREVIEW_READY,
        migration_status="out_of_current_contract",
        replacement_reason="Publication is outside this contract cutoff.",
    ),
    KnowledgeExtractionLegacyPhaseMapping(
        legacy_phase_key=KnowledgeExtractionPhaseKey.RETRIEVAL_EMBEDDINGS_BUILT.value,
        canonical_phase=KnowledgeExtractionCanonicalPhase.CLUSTER_PREVIEW_READY,
        migration_status="out_of_current_contract",
        replacement_reason="Retrieval embeddings are outside this contract cutoff.",
    ),
    KnowledgeExtractionLegacyPhaseMapping(
        legacy_phase_key=KnowledgeExtractionPhaseKey.INTERMEDIATE_ARTIFACTS_CLEANED.value,
        canonical_phase=KnowledgeExtractionCanonicalPhase.CLUSTER_PREVIEW_READY,
        migration_status="out_of_current_contract",
        replacement_reason="Intermediate cleanup is outside this contract cutoff.",
    ),
    KnowledgeExtractionLegacyPhaseMapping(
        legacy_phase_key=KnowledgeExtractionPhaseKey.DONE.value,
        canonical_phase=KnowledgeExtractionCanonicalPhase.CLUSTER_PREVIEW_READY,
        migration_status="out_of_current_contract",
        replacement_reason="Done is outside this contract cutoff.",
    ),
)


def operation_by_key(operation_key: str) -> KnowledgeExtractionOperationContract:
    for operation in DEFAULT_KNOWLEDGE_EXTRACTION_WORKFLOW_CONTRACT.operations:
        if operation.operation_key == operation_key:
            return operation
    raise KeyError(operation_key)


def operations_for_phase(
    phase: KnowledgeExtractionCanonicalPhase,
) -> tuple[KnowledgeExtractionOperationContract, ...]:
    return tuple(
        operation
        for operation in DEFAULT_KNOWLEDGE_EXTRACTION_WORKFLOW_CONTRACT.operations
        if operation.phase is phase
    )


def command_types_used_by_operations() -> frozenset[
    KnowledgeExtractionCanonicalCommandType
]:
    return frozenset(
        operation.command_type
        for operation in DEFAULT_KNOWLEDGE_EXTRACTION_WORKFLOW_CONTRACT.operations
    )


def event_types_used_by_operations() -> frozenset[
    KnowledgeExtractionCanonicalEventType
]:
    used: set[KnowledgeExtractionCanonicalEventType] = set()
    for operation in DEFAULT_KNOWLEDGE_EXTRACTION_WORKFLOW_CONTRACT.operations:
        if operation.success_event_type is not None:
            used.add(operation.success_event_type)
        used.update(operation.failure_event_types)
        used.update(operation.intermediate_event_types)
    return frozenset(used)
