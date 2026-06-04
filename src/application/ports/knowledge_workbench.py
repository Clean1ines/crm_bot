from __future__ import annotations

from datetime import datetime

from typing import Protocol

from src.domain.project_plane.knowledge_workbench import (
    ParallelDrainWorkCounts,
    DocumentSection,
    KnowledgeDocument,
    KnowledgeProcessingRun,
    ParallelSectionBatchPlan,
    SectionBatchQueueItem,
    ProcessingNodeArtifact,
    ProcessingNodeRun,
    FactRegistry,
    CanonicalFact,
    RegistrySnapshot,
    RegistryUpdateApplication,
    ClaimObservationRecord,
    KnowledgeDocumentStatus,
    ProcessingRunStatus,
    ResumePolicy,
    RegistryUpdateProposal,
    RegistryApplicationQueueItem,
    WorkbenchSectionBatchPlan,
    WorkbenchSectionWorkItem,
)


class KnowledgeWorkbenchFreshUploadRepositoryPort(Protocol):
    async def create_document(self, document: KnowledgeDocument) -> None: ...

    async def create_document_sections(
        self,
        sections: tuple[DocumentSection, ...],
    ) -> None: ...

    async def create_processing_run(self, run: KnowledgeProcessingRun) -> None: ...

    async def create_fact_registry(self, registry: FactRegistry) -> None: ...

    async def create_processing_node_run(self, node_run: ProcessingNodeRun) -> None: ...

    async def create_processing_node_artifact(
        self,
        artifact: ProcessingNodeArtifact,
    ) -> None: ...

    async def list_claim_observation_parsed_artifacts(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
    ) -> tuple[ProcessingNodeArtifact, ...]: ...

    async def create_registry_snapshot(self, snapshot: RegistrySnapshot) -> None: ...

    async def create_registry_application_queue_items(
        self,
        items: tuple[RegistryApplicationQueueItem, ...],
    ) -> None: ...

    async def lease_next_registry_application_queue_item(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
        worker_id: str,
        lease_expires_at: object,
    ) -> RegistryApplicationQueueItem | None: ...

    async def mark_registry_application_queue_item_waiting_for_fresh_registry(
        self,
        *,
        queue_item_id: str,
        stale_at_registry_snapshot_id: str,
    ) -> None: ...

    async def mark_registry_application_queue_item_applied(
        self,
        *,
        queue_item_id: str,
        applied_registry_snapshot_id: str,
    ) -> None: ...


class KnowledgeWorkbenchRestoreCheckpointRepositoryPort(Protocol):
    async def create_processing_node_run(self, node_run: ProcessingNodeRun) -> None: ...

    async def create_processing_node_artifact(
        self,
        artifact: ProcessingNodeArtifact,
    ) -> None: ...

    async def list_claim_observation_parsed_artifacts(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
    ) -> tuple[ProcessingNodeArtifact, ...]: ...


class KnowledgeWorkbenchSectionBatchQueueRepositoryPort(Protocol):
    async def create_parallel_section_batch_plan(
        self,
        plan: ParallelSectionBatchPlan,
    ) -> None: ...

    async def list_section_batch_queue_items(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
    ) -> tuple[SectionBatchQueueItem, ...]: ...

    async def get_section_batch_queue_item_by_registry_application_queue_item_id(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
        registry_application_queue_item_id: str,
    ) -> SectionBatchQueueItem | None: ...

    async def update_section_batch_queue_item(
        self,
        item: SectionBatchQueueItem,
    ) -> None: ...


class KnowledgeWorkbenchClaimObservationsRepositoryPort(Protocol):
    async def create_processing_node_run(self, node_run: ProcessingNodeRun) -> None: ...

    async def create_processing_node_artifact(
        self,
        artifact: ProcessingNodeArtifact,
    ) -> None: ...

    async def list_claim_observation_parsed_artifacts(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
    ) -> tuple[ProcessingNodeArtifact, ...]: ...

    async def sync_processing_run_llm_usage_totals(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
    ) -> None: ...

    async def persist_claim_observations_generation_error_lifecycle(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
        document_status: KnowledgeDocumentStatus,
        processing_run_status: ProcessingRunStatus,
        resume_policy: ResumePolicy,
        error_kind: str,
        error_report_id: str,
        user_message: str,
        internal_error: str,
    ) -> None: ...

    async def create_claim_observations(
        self,
        claim_observations: tuple[ClaimObservationRecord, ...],
    ) -> None: ...

    async def create_registry_snapshot(self, snapshot: RegistrySnapshot) -> None: ...


class KnowledgeWorkbenchRegistryApplicationRepositoryPort(Protocol):
    async def get_fact_registry_for_run(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
    ) -> FactRegistry | None: ...

    async def list_canonical_facts(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
    ) -> tuple[CanonicalFact, ...]: ...

    async def get_latest_registry_snapshot(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
    ) -> RegistrySnapshot | None: ...

    async def list_claim_observations_by_ids(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
        claim_input_refs: tuple[str, ...],
    ) -> tuple[ClaimObservationRecord, ...]: ...
    async def create_processing_node_run(self, node_run: ProcessingNodeRun) -> None: ...

    async def create_processing_node_artifact(
        self,
        artifact: ProcessingNodeArtifact,
    ) -> None: ...

    async def list_claim_observation_parsed_artifacts(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
    ) -> tuple[ProcessingNodeArtifact, ...]: ...

    async def sync_processing_run_llm_usage_totals(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
    ) -> None: ...

    async def persist_final_reconciliation_generation_error_lifecycle(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
        node_run_id: str,
        document_status: KnowledgeDocumentStatus,
        processing_run_status: ProcessingRunStatus,
        resume_policy: ResumePolicy,
        error_kind: str,
        user_message: str,
        internal_error: str,
    ) -> None: ...

    async def persist_registry_merge_generation_error_lifecycle(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
        node_run_id: str,
        document_status: KnowledgeDocumentStatus,
        processing_run_status: ProcessingRunStatus,
        resume_policy: ResumePolicy,
        error_kind: str,
        user_message: str,
        internal_error: str,
    ) -> None: ...

    async def upsert_canonical_facts(
        self,
        entries: tuple[CanonicalFact, ...],
    ) -> None: ...

    async def create_registry_update_proposals(
        self,
        proposals: tuple[RegistryUpdateProposal, ...],
    ) -> None: ...

    async def create_registry_update_applications(
        self,
        applications: tuple[RegistryUpdateApplication, ...],
    ) -> None: ...

    async def create_registry_snapshot(self, snapshot: RegistrySnapshot) -> None: ...

    async def restore_stale_section_work_item_leases(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
        now: datetime,
    ) -> int: ...

    async def lease_next_ready_section_work_item(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
        worker_id: str,
        lease_expires_at: datetime,
        now: datetime,
    ) -> SectionBatchQueueItem | None: ...

    async def restore_stale_registry_application_work_item_leases(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
        now: datetime,
    ) -> int: ...

    async def lease_next_ready_registry_application_work_item(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
        worker_id: str,
        lease_expires_at: datetime,
        now: datetime,
    ) -> RegistryApplicationQueueItem | None: ...

    async def update_registry_application_queue_item(
        self,
        item: RegistryApplicationQueueItem,
    ) -> None: ...

    async def get_parallel_processing_drain_counts(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
    ) -> ParallelDrainWorkCounts: ...

    async def has_completed_fact_registry_canonicalization(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
    ) -> bool: ...

    async def mark_parallel_processing_completed(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
    ) -> None: ...


class KnowledgeWorkbenchSectionBatchPlanningRepositoryPort(Protocol):
    async def create_processing_node_run(self, node_run: ProcessingNodeRun) -> None: ...

    async def create_processing_node_artifact(
        self,
        artifact: ProcessingNodeArtifact,
    ) -> None: ...

    async def list_claim_observation_parsed_artifacts(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
    ) -> tuple[ProcessingNodeArtifact, ...]: ...

    async def create_section_batch_plan(
        self,
        plan: WorkbenchSectionBatchPlan,
    ) -> None: ...

    async def create_section_work_items(
        self,
        items: tuple[WorkbenchSectionWorkItem, ...],
    ) -> None: ...

    async def update_section_work_items(
        self,
        items: tuple[WorkbenchSectionWorkItem, ...],
    ) -> None: ...

    async def get_latest_section_batch_plan(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
    ) -> WorkbenchSectionBatchPlan | None: ...

    async def list_section_work_items(
        self,
        *,
        batch_plan_id: str,
    ) -> tuple[WorkbenchSectionWorkItem, ...]: ...


class KnowledgeWorkbenchRuntimePublicationRepositoryPort(Protocol):
    async def get_document(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> KnowledgeDocument | None: ...

    async def list_surfaces_for_curation_session(
        self,
        *,
        project_id: str,
        document_id: str,
        curation_session_id: str,
    ) -> tuple[object, ...]: ...

    async def update_(
        self,
        surfaces: tuple[object, ...],
    ) -> None: ...

    async def create_runtime_retrieval_entries(
        self,
        entries: tuple[object, ...],
    ) -> None: ...
