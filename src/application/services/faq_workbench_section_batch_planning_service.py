from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from src.application.ports.knowledge_workbench import (
    KnowledgeWorkbenchSectionBatchPlanningRepositoryPort,
)
from src.domain.project_plane.knowledge_workbench import (
    DocumentSection,
    DomainInvariantError,
    JsonValue,
    ProcessingNodeArtifact,
    ProcessingNodeArtifactType,
    ProcessingNodeKind,
    ProcessingNodeName,
    ProcessingNodeRun,
    ProcessingNodeStatus,
    RegistrySnapshot,
    WorkbenchSectionBatchPlan,
    WorkbenchSectionBatchPlanStatus,
    WorkbenchSectionWorkItem,
    WorkbenchSectionWorkItemStatus,
    assign_section_lane_id,
    restore_stale_section_work_item_leases,
    runnable_section_work_items,
)


class IdFactory(Protocol):
    def new_id(self, prefix: str) -> str: ...


class TimeProvider(Protocol):
    def now(self) -> datetime: ...


@dataclass(frozen=True, slots=True)
class SystemTimeProvider:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class ProcessParallelSectionBatchCommand:
    sections: tuple[DocumentSection, ...]
    latest_registry_snapshot: RegistrySnapshot
    max_concurrency: int = 3
    existing_plan: WorkbenchSectionBatchPlan | None = None
    existing_work_items: tuple[WorkbenchSectionWorkItem, ...] = ()


@dataclass(frozen=True, slots=True)
class ProcessParallelSectionBatchResult:
    node_run: ProcessingNodeRun
    input_artifact: ProcessingNodeArtifact
    output_artifact: ProcessingNodeArtifact
    batch_plan: WorkbenchSectionBatchPlan
    work_items: tuple[WorkbenchSectionWorkItem, ...]
    runnable_work_items: tuple[WorkbenchSectionWorkItem, ...]

    @property
    def runnable_section_ids(self) -> tuple[str, ...]:
        return tuple(item.section_id for item in self.runnable_work_items)


class FaqWorkbenchSectionBatchPlanningService:
    def __init__(
        self,
        repository: KnowledgeWorkbenchSectionBatchPlanningRepositoryPort,
        *,
        id_factory: IdFactory,
        time_provider: TimeProvider | None = None,
    ) -> None:
        self._repository = repository
        self._id_factory = id_factory
        self._time_provider = time_provider or SystemTimeProvider()

    async def process_parallel_section_batch(
        self,
        command: ProcessParallelSectionBatchCommand,
    ) -> ProcessParallelSectionBatchResult:
        self._validate_command(command)
        now = self._time_provider.now()
        snapshot = command.latest_registry_snapshot

        node_run_id = self._id_factory.new_id("node-run")
        input_artifact_id = self._id_factory.new_id("artifact")
        output_artifact_id = self._id_factory.new_id("artifact")

        if command.existing_plan is None:
            batch_plan = self._new_batch_plan(command=command, now=now)
            work_items = self._new_work_items(
                batch_plan=batch_plan,
                sections=command.sections,
                snapshot=snapshot,
                now=now,
            )
            created_new_plan = True
            restored_items = work_items
        else:
            batch_plan = command.existing_plan
            work_items = command.existing_work_items
            created_new_plan = False
            restored_items = restore_stale_section_work_item_leases(
                items=work_items,
                now=now,
            )

        runnable_items = runnable_section_work_items(restored_items)

        node_run = ProcessingNodeRun(
            node_run_id=node_run_id,
            processing_run_id=snapshot.processing_run_id,
            project_id=snapshot.project_id,
            document_id=snapshot.document_id,
            node_name=ProcessingNodeName.PROCESS_PARALLEL_SECTION_BATCH,
            node_kind=ProcessingNodeKind.CONTROL_FLOW,
            status=ProcessingNodeStatus.COMPLETED,
            input_snapshot_id=input_artifact_id,
            output_snapshot_id=output_artifact_id,
            started_at=now,
            completed_at=now,
        )

        input_artifact = ProcessingNodeArtifact(
            artifact_id=input_artifact_id,
            node_run_id=node_run_id,
            processing_run_id=snapshot.processing_run_id,
            project_id=snapshot.project_id,
            document_id=snapshot.document_id,
            artifact_type=ProcessingNodeArtifactType.INPUT_SNAPSHOT,
            payload_json=self._input_payload(command),
            schema_version=1,
            created_at=now,
            metadata={
                "node": ProcessingNodeName.PROCESS_PARALLEL_SECTION_BATCH.value,
                "registry_snapshot_id": snapshot.snapshot_id,
            },
        )

        output_artifact = ProcessingNodeArtifact(
            artifact_id=output_artifact_id,
            node_run_id=node_run_id,
            processing_run_id=snapshot.processing_run_id,
            project_id=snapshot.project_id,
            document_id=snapshot.document_id,
            artifact_type=ProcessingNodeArtifactType.DETERMINISTIC_RESULT,
            payload_json=self._output_payload(
                batch_plan=batch_plan,
                work_items=restored_items,
                runnable_items=runnable_items,
                created_new_plan=created_new_plan,
            ),
            schema_version=1,
            created_at=now,
            metadata={
                "node": ProcessingNodeName.PROCESS_PARALLEL_SECTION_BATCH.value,
                "batch_plan_id": batch_plan.batch_plan_id,
                "runnable_work_item_count": len(runnable_items),
                "max_concurrency": batch_plan.max_concurrency,
            },
        )

        await self._repository.create_processing_node_run(node_run)
        await self._repository.create_processing_node_artifact(input_artifact)

        if created_new_plan:
            await self._repository.create_section_batch_plan(batch_plan)
            await self._repository.create_section_work_items(restored_items)
        elif restored_items != work_items:
            await self._repository.update_section_work_items(restored_items)

        await self._repository.create_processing_node_artifact(output_artifact)

        return ProcessParallelSectionBatchResult(
            node_run=node_run,
            input_artifact=input_artifact,
            output_artifact=output_artifact,
            batch_plan=batch_plan,
            work_items=restored_items,
            runnable_work_items=runnable_items,
        )

    def _new_batch_plan(
        self,
        *,
        command: ProcessParallelSectionBatchCommand,
        now: datetime,
    ) -> WorkbenchSectionBatchPlan:
        snapshot = command.latest_registry_snapshot
        return WorkbenchSectionBatchPlan(
            batch_plan_id=self._id_factory.new_id("section-batch-plan"),
            processing_run_id=snapshot.processing_run_id,
            project_id=snapshot.project_id,
            document_id=snapshot.document_id,
            base_snapshot_id=snapshot.snapshot_id,
            base_snapshot_sequence_number=snapshot.sequence_number,
            max_concurrency=command.max_concurrency,
            status=WorkbenchSectionBatchPlanStatus.PLANNED,
            created_at=now,
            updated_at=now,
        )

    def _new_work_items(
        self,
        *,
        batch_plan: WorkbenchSectionBatchPlan,
        sections: tuple[DocumentSection, ...],
        snapshot: RegistrySnapshot,
        now: datetime,
    ) -> tuple[WorkbenchSectionWorkItem, ...]:
        sorted_sections = tuple(
            sorted(sections, key=lambda section: section.section_index)
        )
        total_count = len(sorted_sections)

        return tuple(
            WorkbenchSectionWorkItem(
                work_item_id=self._id_factory.new_id("section-work-item"),
                batch_plan_id=batch_plan.batch_plan_id,
                processing_run_id=snapshot.processing_run_id,
                project_id=snapshot.project_id,
                document_id=snapshot.document_id,
                section_id=section.section_id,
                section_index=section.section_index,
                lane_id=assign_section_lane_id(
                    position=position,
                    total_count=total_count,
                    max_concurrency=batch_plan.max_concurrency,
                ),
                status=WorkbenchSectionWorkItemStatus.PENDING,
                idempotency_key=self._idempotency_key(
                    batch_plan=batch_plan,
                    section=section,
                    snapshot=snapshot,
                ),
                based_on_snapshot_id=snapshot.snapshot_id,
                based_on_snapshot_sequence_number=snapshot.sequence_number,
                created_at=now,
                updated_at=now,
            )
            for position, section in enumerate(sorted_sections)
        )

    def _validate_command(self, command: ProcessParallelSectionBatchCommand) -> None:
        if command.max_concurrency < 1:
            raise DomainInvariantError("max_concurrency must be positive")

        snapshot = command.latest_registry_snapshot
        if not snapshot.snapshot_id:
            raise DomainInvariantError("section batch requires registry snapshot")

        if command.existing_plan is not None:
            plan = command.existing_plan
            if plan.project_id != snapshot.project_id:
                raise DomainInvariantError("batch plan project mismatch")
            if plan.document_id != snapshot.document_id:
                raise DomainInvariantError("batch plan document mismatch")
            if plan.processing_run_id != snapshot.processing_run_id:
                raise DomainInvariantError("batch plan processing run mismatch")

        section_ids = set[str]()
        for section in command.sections:
            if section.project_id != snapshot.project_id:
                raise DomainInvariantError("section batch project mismatch")
            if section.document_id != snapshot.document_id:
                raise DomainInvariantError("section batch document mismatch")
            if section.section_id in section_ids:
                raise DomainInvariantError("duplicate section in batch plan")
            section_ids.add(section.section_id)

        existing_ids = {item.section_id for item in command.existing_work_items}
        unknown_existing_ids = existing_ids - section_ids
        if unknown_existing_ids:
            raise DomainInvariantError(
                "existing section work item references unknown section"
            )

    def _idempotency_key(
        self,
        *,
        batch_plan: WorkbenchSectionBatchPlan,
        section: DocumentSection,
        snapshot: RegistrySnapshot,
    ) -> str:
        return (
            f"{snapshot.project_id}:"
            f"{snapshot.document_id}:"
            f"{snapshot.processing_run_id}:"
            f"{batch_plan.batch_plan_id}:"
            f"{section.section_id}:"
            f"{snapshot.snapshot_id}"
        )

    def _input_payload(
        self,
        command: ProcessParallelSectionBatchCommand,
    ) -> JsonValue:
        snapshot = command.latest_registry_snapshot
        return {
            "node": ProcessingNodeName.PROCESS_PARALLEL_SECTION_BATCH.value,
            "registry_snapshot_id": snapshot.snapshot_id,
            "registry_snapshot_sequence_number": snapshot.sequence_number,
            "max_concurrency": command.max_concurrency,
            "existing_batch_plan_id": (
                command.existing_plan.batch_plan_id
                if command.existing_plan is not None
                else None
            ),
            "section_ids": [
                section.section_id
                for section in sorted(
                    command.sections,
                    key=lambda item: item.section_index,
                )
            ],
        }

    def _output_payload(
        self,
        *,
        batch_plan: WorkbenchSectionBatchPlan,
        work_items: tuple[WorkbenchSectionWorkItem, ...],
        runnable_items: tuple[WorkbenchSectionWorkItem, ...],
        created_new_plan: bool,
    ) -> JsonValue:
        return {
            "node": ProcessingNodeName.PROCESS_PARALLEL_SECTION_BATCH.value,
            "created_new_plan": created_new_plan,
            "batch_plan": {
                "batch_plan_id": batch_plan.batch_plan_id,
                "base_snapshot_id": batch_plan.base_snapshot_id,
                "base_snapshot_sequence_number": (
                    batch_plan.base_snapshot_sequence_number
                ),
                "max_concurrency": batch_plan.max_concurrency,
                "status": batch_plan.status.value,
            },
            "work_items": [
                {
                    "work_item_id": item.work_item_id,
                    "section_id": item.section_id,
                    "section_index": item.section_index,
                    "lane_id": item.lane_id,
                    "status": item.status.value,
                    "based_on_snapshot_id": item.based_on_snapshot_id,
                    "based_on_snapshot_sequence_number": (
                        item.based_on_snapshot_sequence_number
                    ),
                    "applied_snapshot_id": item.applied_snapshot_id,
                    "idempotency_key": item.idempotency_key,
                }
                for item in work_items
            ],
            "runnable_work_item_ids": [item.work_item_id for item in runnable_items],
            "runnable_section_ids": [item.section_id for item in runnable_items],
        }
