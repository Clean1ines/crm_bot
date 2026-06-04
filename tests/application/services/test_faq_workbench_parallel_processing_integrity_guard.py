from __future__ import annotations

from dataclasses import dataclass

import pytest

from src.application.services.faq_workbench_parallel_processing_coordinator_service import (
    FaqWorkbenchParallelProcessingCoordinatorService,
    ParallelProcessingIntegrityError,
    ProcessParallelCanonicalizationBarrierCommand,
    ProcessParallelRegistryApplicationWorkItemCommand,
    ProcessParallelSectionWorkItemCommand,
    RunParallelWorkbenchProcessingCommand,
)
from src.domain.project_plane.knowledge_workbench import (
    ParallelDrainWorkCounts,
    ParallelProcessingIntegrityCounts,
)


@dataclass(frozen=True, slots=True)
class Outcome:
    outcome: str


class NoWorkSectionProcessor:
    async def process_next_section_work_item(
        self,
        command: ProcessParallelSectionWorkItemCommand,
    ) -> Outcome:
        return Outcome("no_work")


class NoWorkCanonicalizationBarrier:
    async def process_document_canonicalization_barrier(
        self,
        command: ProcessParallelCanonicalizationBarrierCommand,
    ) -> Outcome:
        return Outcome("no_work")


class NoWorkRegistryProcessor:
    async def process_next_registry_application_work_item(
        self,
        command: ProcessParallelRegistryApplicationWorkItemCommand,
    ) -> Outcome:
        return Outcome("no_work")


class DrainedCountsProvider:
    async def get_parallel_processing_drain_counts(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
    ) -> ParallelDrainWorkCounts:
        return ParallelDrainWorkCounts()


@dataclass(slots=True)
class StaticIntegrityCountsProvider:
    counts: ParallelProcessingIntegrityCounts

    async def get_parallel_processing_integrity_counts(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
    ) -> ParallelProcessingIntegrityCounts:
        return self.counts


@dataclass(slots=True)
class LifecycleCompletionRecorder:
    completed: bool = False

    async def mark_parallel_processing_completed(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
    ) -> None:
        self.completed = True


@pytest.mark.asyncio
async def test_parallel_processing_refuses_false_success_when_sections_have_no_queue_items() -> (
    None
):
    lifecycle = LifecycleCompletionRecorder()
    coordinator = FaqWorkbenchParallelProcessingCoordinatorService(
        section_processor=NoWorkSectionProcessor(),
        registry_processor=NoWorkRegistryProcessor(),
        canonicalization_barrier_processor=NoWorkCanonicalizationBarrier(),
        drain_counts_provider=DrainedCountsProvider(),
        integrity_counts_provider=StaticIntegrityCountsProvider(
            ParallelProcessingIntegrityCounts(
                document_sections_total=3,
                section_queue_items_total=0,
                claim_observation_artifacts_total=0,
                canonicalization_artifacts_total=0,
            )
        ),
        lifecycle_completion_port=lifecycle,
    )

    with pytest.raises(ParallelProcessingIntegrityError) as exc_info:
        await coordinator.run_parallel_processing(
            RunParallelWorkbenchProcessingCommand(
                project_id="project-1",
                document_id="document-1",
                processing_run_id="processing-run-1",
                section_worker_count=3,
                max_cycles=1,
            )
        )

    assert lifecycle.completed is False
    assert exc_info.value.document_sections_total == 3
    assert exc_info.value.section_queue_items_total == 0
    assert "section_queue_items_total=0" in str(exc_info.value)


@pytest.mark.asyncio
async def test_parallel_processing_can_complete_when_sections_match_queue_items() -> (
    None
):
    lifecycle = LifecycleCompletionRecorder()
    coordinator = FaqWorkbenchParallelProcessingCoordinatorService(
        section_processor=NoWorkSectionProcessor(),
        registry_processor=NoWorkRegistryProcessor(),
        canonicalization_barrier_processor=NoWorkCanonicalizationBarrier(),
        drain_counts_provider=DrainedCountsProvider(),
        integrity_counts_provider=StaticIntegrityCountsProvider(
            ParallelProcessingIntegrityCounts(
                document_sections_total=3,
                section_queue_items_total=3,
                claim_observation_artifacts_total=3,
                canonicalization_artifacts_total=1,
            )
        ),
        lifecycle_completion_port=lifecycle,
    )

    result = await coordinator.run_parallel_processing(
        RunParallelWorkbenchProcessingCommand(
            project_id="project-1",
            document_id="document-1",
            processing_run_id="processing-run-1",
            section_worker_count=3,
            max_cycles=1,
        )
    )

    assert result.cycle_count == 1
    assert lifecycle.completed is True
