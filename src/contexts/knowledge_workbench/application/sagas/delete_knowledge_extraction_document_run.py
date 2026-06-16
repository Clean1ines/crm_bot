from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class DeleteKnowledgeExtractionDocumentRunCommand:
    project_id: UUID
    source_document_ref: str
    actor_user_id: UUID
    occurred_at: datetime


@dataclass(frozen=True)
class DocumentRunRefs:
    project_id: str
    source_document_ref: str
    exists: bool
    workflow_run_ids: tuple[str, ...]
    processing_run_ids: tuple[str, ...]
    source_unit_refs: tuple[str, ...]
    observation_refs: tuple[str, ...]
    work_item_ids: tuple[str, ...]
    attempt_ids: tuple[str, ...]
    llm_task_ids: tuple[str, ...]
    llm_attempt_ids: tuple[str, ...]
    curation_workspace_refs: tuple[str, ...]


@dataclass(frozen=True)
class DeletedWorkbenchDocumentRunCounts:
    source_documents: int = 0
    source_units: int = 0
    workbench_documents: int = 0
    workbench_child_rows: int = 0
    workflow_runs: int = 0
    workflow_commands: int = 0
    workflow_outbox_events: int = 0
    workflow_progress_snapshots: int = 0
    timeline_entries: int = 0
    resource_usage_snapshots: int = 0
    execution_work_items: int = 0
    execution_work_item_attempts: int = 0
    execution_work_item_schedules: int = 0
    execution_attempt_dispatches: int = 0
    draft_claims: int = 0
    draft_claim_possible_questions: int = 0
    draft_claim_provenance: int = 0
    draft_claim_embeddings: int = 0
    clusters: int = 0
    compaction_items: int = 0
    curation_workspaces: int = 0
    curation_items: int = 0
    runtime_entries: int = 0
    runtime_embeddings: int = 0
    publications: int = 0
    llm_artifacts: int = 0
    capacity_rows: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "source_documents": self.source_documents,
            "source_units": self.source_units,
            "workbench_documents": self.workbench_documents,
            "workbench_child_rows": self.workbench_child_rows,
            "workflow_runs": self.workflow_runs,
            "workflow_commands": self.workflow_commands,
            "workflow_outbox_events": self.workflow_outbox_events,
            "workflow_progress_snapshots": self.workflow_progress_snapshots,
            "timeline_entries": self.timeline_entries,
            "resource_usage_snapshots": self.resource_usage_snapshots,
            "execution_work_items": self.execution_work_items,
            "execution_work_item_attempts": self.execution_work_item_attempts,
            "execution_work_item_schedules": self.execution_work_item_schedules,
            "execution_attempt_dispatches": self.execution_attempt_dispatches,
            "draft_claims": self.draft_claims,
            "draft_claim_possible_questions": self.draft_claim_possible_questions,
            "draft_claim_provenance": self.draft_claim_provenance,
            "draft_claim_embeddings": self.draft_claim_embeddings,
            "clusters": self.clusters,
            "compaction_items": self.compaction_items,
            "curation_workspaces": self.curation_workspaces,
            "curation_items": self.curation_items,
            "runtime_entries": self.runtime_entries,
            "runtime_embeddings": self.runtime_embeddings,
            "publications": self.publications,
            "llm_artifacts": self.llm_artifacts,
            "capacity_rows": self.capacity_rows,
        }


@dataclass(frozen=True)
class DeleteKnowledgeExtractionDocumentRunResult:
    deleted: bool
    source_document_ref: str
    workflow_run_ids: tuple[str, ...]
    deleted_counts: DeletedWorkbenchDocumentRunCounts


class WorkbenchDocumentRunCleanupRepositoryPort(Protocol):
    async def collect_document_run_refs(
        self,
        *,
        project_id: UUID,
        source_document_ref: str,
    ) -> DocumentRunRefs: ...

    async def delete_document_run(
        self,
        refs: DocumentRunRefs,
    ) -> DeletedWorkbenchDocumentRunCounts: ...


class DeleteKnowledgeExtractionDocumentRun:
    def __init__(
        self,
        cleanup_repository: WorkbenchDocumentRunCleanupRepositoryPort,
    ) -> None:
        self._cleanup_repository = cleanup_repository

    async def execute(
        self,
        command: DeleteKnowledgeExtractionDocumentRunCommand,
    ) -> DeleteKnowledgeExtractionDocumentRunResult:
        refs = await self._cleanup_repository.collect_document_run_refs(
            project_id=command.project_id,
            source_document_ref=command.source_document_ref,
        )
        if not refs.exists:
            return DeleteKnowledgeExtractionDocumentRunResult(
                deleted=False,
                source_document_ref=command.source_document_ref,
                workflow_run_ids=(),
                deleted_counts=DeletedWorkbenchDocumentRunCounts(),
            )

        counts = await self._cleanup_repository.delete_document_run(refs)
        return DeleteKnowledgeExtractionDocumentRunResult(
            deleted=True,
            source_document_ref=command.source_document_ref,
            workflow_run_ids=refs.workflow_run_ids,
            deleted_counts=counts,
        )


def deleted_counts_from_mapping(
    values: Mapping[str, int],
) -> DeletedWorkbenchDocumentRunCounts:
    return DeletedWorkbenchDocumentRunCounts(
        source_documents=values.get("source_documents", 0),
        source_units=values.get("source_units", 0),
        workbench_documents=values.get("workbench_documents", 0),
        workbench_child_rows=values.get("workbench_child_rows", 0),
        workflow_runs=values.get("workflow_runs", 0),
        workflow_commands=values.get("workflow_commands", 0),
        workflow_outbox_events=values.get("workflow_outbox_events", 0),
        workflow_progress_snapshots=values.get("workflow_progress_snapshots", 0),
        timeline_entries=values.get("timeline_entries", 0),
        resource_usage_snapshots=values.get("resource_usage_snapshots", 0),
        execution_work_items=values.get("execution_work_items", 0),
        execution_work_item_attempts=values.get("execution_work_item_attempts", 0),
        execution_work_item_schedules=values.get("execution_work_item_schedules", 0),
        execution_attempt_dispatches=values.get("execution_attempt_dispatches", 0),
        draft_claims=values.get("draft_claims", 0),
        draft_claim_possible_questions=values.get("draft_claim_possible_questions", 0),
        draft_claim_provenance=values.get("draft_claim_provenance", 0),
        draft_claim_embeddings=values.get("draft_claim_embeddings", 0),
        clusters=values.get("clusters", 0),
        compaction_items=values.get("compaction_items", 0),
        curation_workspaces=values.get("curation_workspaces", 0),
        curation_items=values.get("curation_items", 0),
        runtime_entries=values.get("runtime_entries", 0),
        runtime_embeddings=values.get("runtime_embeddings", 0),
        publications=values.get("publications", 0),
        llm_artifacts=values.get("llm_artifacts", 0),
        capacity_rows=values.get("capacity_rows", 0),
    )
