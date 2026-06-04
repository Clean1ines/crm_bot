from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from src.application.workbench.dto import WorkbenchProcessDocumentJobPayloadDto
from src.domain.project_plane.knowledge_workbench import (
    DocumentSection,
    FactRegistry,
    KnowledgeDocument,
    KnowledgeProcessingRun,
    ParallelSectionBatchPlan,
    ProcessingNodeArtifact,
    ProcessingNodeRun,
    RegistrySnapshot,
    SectionBatchQueueItem,
    WorkbenchSectionBatchPlan,
    WorkbenchSectionWorkItem,
)
from src.domain.project_plane.knowledge_workbench.parallel_drain_policy import (
    ParallelDrainWorkCounts,
)


@dataclass(frozen=True, slots=True)
class FixedTimeProvider:
    value: datetime

    def now(self) -> datetime:
        return self.value


@dataclass(slots=True)
class InMemoryWorkbenchQueue:
    payloads: list[WorkbenchProcessDocumentJobPayloadDto] = field(default_factory=list)

    async def enqueue_process_workbench_document(
        self,
        payload: WorkbenchProcessDocumentJobPayloadDto,
    ) -> None:
        self.payloads.append(payload)


@dataclass(slots=True)
class InMemoryWorkbenchRepository:
    documents: list[KnowledgeDocument] = field(default_factory=list)
    sections: list[DocumentSection] = field(default_factory=list)
    processing_runs: list[KnowledgeProcessingRun] = field(default_factory=list)
    fact_registries: list[FactRegistry] = field(default_factory=list)
    processing_node_runs: list[ProcessingNodeRun] = field(default_factory=list)
    processing_node_artifacts: list[ProcessingNodeArtifact] = field(
        default_factory=list
    )
    registry_snapshots: list[RegistrySnapshot] = field(default_factory=list)
    section_batch_plans: list[WorkbenchSectionBatchPlan] = field(default_factory=list)
    section_work_items: list[WorkbenchSectionWorkItem] = field(default_factory=list)
    parallel_section_batch_plans: list[ParallelSectionBatchPlan] = field(
        default_factory=list
    )
    section_batch_queue_items: list[SectionBatchQueueItem] = field(default_factory=list)

    async def create_document(
        self,
        document: KnowledgeDocument,
    ) -> None:
        self.documents.append(document)

    async def create_document_sections(
        self,
        sections: tuple[DocumentSection, ...],
    ) -> None:
        self.sections.extend(sections)

    async def create_processing_run(
        self,
        processing_run: KnowledgeProcessingRun,
    ) -> None:
        self.processing_runs.append(processing_run)

    async def create_fact_registry(
        self,
        registry: FactRegistry,
    ) -> None:
        self.fact_registries.append(registry)

    async def create_processing_node_run(
        self,
        node_run: ProcessingNodeRun,
    ) -> None:
        self.processing_node_runs.append(node_run)

    async def create_processing_node_artifact(
        self,
        artifact: ProcessingNodeArtifact,
    ) -> None:
        self.processing_node_artifacts.append(artifact)

    async def create_registry_snapshot(
        self,
        snapshot: RegistrySnapshot,
    ) -> None:
        self.registry_snapshots.append(snapshot)

    async def create_fresh_upload(
        self,
        *,
        document: KnowledgeDocument,
        sections: tuple[DocumentSection, ...],
        processing_run: KnowledgeProcessingRun,
    ) -> None:
        await self.create_document(document)
        await self.create_document_sections(sections)
        await self.create_processing_run(processing_run)

    async def create_section_batch_plan(
        self,
        plan: WorkbenchSectionBatchPlan,
    ) -> None:
        self.section_batch_plans.append(plan)

    async def create_section_work_items(
        self,
        items: tuple[WorkbenchSectionWorkItem, ...],
    ) -> None:
        self.section_work_items.extend(items)

    async def create_parallel_section_batch_plan(
        self,
        plan: ParallelSectionBatchPlan,
    ) -> None:
        self.parallel_section_batch_plans.append(plan)
        self.section_batch_plans.append(plan)
        self.section_batch_queue_items.extend(plan.queue_items)
        self.section_batch_queue_items.sort(
            key=lambda item: (
                item.project_id,
                item.document_id,
                item.processing_run_id,
                item.lane_index,
                item.section_index,
                item.queue_item_id,
            )
        )

    async def create_section_batch_queue_items(
        self,
        items: tuple[SectionBatchQueueItem, ...],
    ) -> None:
        self.section_batch_queue_items.extend(items)

    async def list_section_batch_queue_items(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str | None = None,
    ) -> tuple[SectionBatchQueueItem, ...]:
        return tuple(
            item
            for item in self.section_batch_queue_items
            if item.project_id == project_id
            and item.document_id == document_id
            and (
                processing_run_id is None or item.processing_run_id == processing_run_id
            )
        )

    async def update_section_batch_queue_item(
        self,
        item: SectionBatchQueueItem,
    ) -> None:
        self.section_batch_queue_items = [
            item if existing.queue_item_id == item.queue_item_id else existing
            for existing in self.section_batch_queue_items
        ]
        self.section_batch_queue_items.sort(
            key=lambda existing: (
                existing.project_id,
                existing.document_id,
                existing.processing_run_id,
                existing.lane_index,
                existing.section_index,
                existing.queue_item_id,
            )
        )

    async def get_parallel_processing_drain_counts(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
    ) -> ParallelDrainWorkCounts:
        items = await self.list_section_batch_queue_items(
            project_id=project_id,
            document_id=document_id,
            processing_run_id=processing_run_id,
        )

        queued = sum(1 for item in items if item.status.value == "queued")
        leased = sum(1 for item in items if item.status.value == "leased")
        claim_observations_persisted = sum(
            1 for item in items if item.status.value == "claim_observations_persisted"
        )
        registry_application_queued = sum(
            1 for item in items if item.status.value == "registry_application_queued"
        )
        registry_application_applied = sum(
            1 for item in items if item.status.value == "registry_application_applied"
        )
        failed = sum(1 for item in items if item.status.value == "failed")
        cancelled = sum(1 for item in items if item.status.value == "cancelled")

        return ParallelDrainWorkCounts(
            queued=queued,
            leased=leased,
            claim_observations_persisted=claim_observations_persisted,
            registry_application_queued=registry_application_queued,
            registry_application_applied=registry_application_applied,
            failed=failed,
            cancelled=cancelled,
        )

    async def save_section_batch_queue_item(
        self,
        item: SectionBatchQueueItem,
    ) -> None:
        await self.update_section_batch_queue_item(item)

    async def save_section_batch_queue_items(
        self,
        items: tuple[SectionBatchQueueItem, ...],
    ) -> None:
        for item in items:
            await self.update_section_batch_queue_item(item)

    async def mark_section_batch_queue_item_leased(
        self,
        *,
        queue_item_id: str,
        worker_id: str,
        leased_until: datetime,
    ) -> SectionBatchQueueItem | None:
        from src.domain.project_plane.knowledge_workbench import (
            mark_section_batch_item_leased,
        )

        for item in self.section_batch_queue_items:
            if item.queue_item_id != queue_item_id:
                continue
            updated = mark_section_batch_item_leased(
                queue_item=item,
                worker_id=worker_id,
                lease_expires_at=leased_until,
            )
            await self.update_section_batch_queue_item(updated)
            return updated
        return None
