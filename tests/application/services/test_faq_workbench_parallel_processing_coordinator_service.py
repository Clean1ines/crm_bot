from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from src.domain.project_plane.knowledge_workbench import ParallelDrainWorkCounts

from src.application.services.faq_workbench_parallel_processing_coordinator_service import (
    FaqWorkbenchParallelProcessingCoordinatorService,
    ProcessParallelCanonicalizationBarrierCommand,
    ProcessParallelRegistryApplicationWorkItemCommand,
    ProcessParallelSectionWorkItemCommand,
    RunParallelWorkbenchProcessingCommand,
)


@dataclass(slots=True)
class FakeSectionProcessor:
    outcomes: list[str]
    commands: list[ProcessParallelSectionWorkItemCommand] = field(default_factory=list)

    async def process_next_section_work_item(
        self,
        command: ProcessParallelSectionWorkItemCommand,
    ) -> str:
        self.commands.append(command)
        if self.outcomes:
            return self.outcomes.pop(0)
        return "no_work"


@dataclass(slots=True)
class FakeCanonicalizationBarrierProcessor:
    outcomes: list[str]
    commands: list[ProcessParallelCanonicalizationBarrierCommand] = field(
        default_factory=list
    )

    async def process_document_canonicalization_barrier(
        self,
        command: ProcessParallelCanonicalizationBarrierCommand,
    ) -> str:
        self.commands.append(command)
        if self.outcomes:
            return self.outcomes.pop(0)
        return "no_work"


@dataclass(slots=True)
class FakeRegistryProcessor:
    outcomes: list[str]
    commands: list[ProcessParallelRegistryApplicationWorkItemCommand] = field(
        default_factory=list
    )

    async def process_next_registry_application_work_item(
        self,
        command: ProcessParallelRegistryApplicationWorkItemCommand,
    ) -> str:
        self.commands.append(command)
        if self.outcomes:
            return self.outcomes.pop(0)
        return "no_work"


@dataclass(slots=True)
class FakeDrainCountsProvider:
    counts: list[ParallelDrainWorkCounts]
    calls: list[dict[str, str]] = field(default_factory=list)

    async def get_parallel_processing_drain_counts(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
    ) -> ParallelDrainWorkCounts:
        self.calls.append(
            {
                "project_id": project_id,
                "document_id": document_id,
                "processing_run_id": processing_run_id,
            }
        )
        if self.counts:
            return self.counts.pop(0)
        return ParallelDrainWorkCounts()



@dataclass(slots=True)
class FakeLifecycleCompletionPort:
    calls: list[dict[str, str]] = field(default_factory=list)

    async def mark_parallel_processing_completed(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
    ) -> None:
        self.calls.append(
            {
                "project_id": project_id,
                "document_id": document_id,
                "processing_run_id": processing_run_id,
            }
        )


@pytest.mark.asyncio
async def test_parallel_processing_runs_canonicalization_barrier_after_section_wave_is_drained() -> None:
    section_processor = FakeSectionProcessor(outcomes=["no_work", "no_work"])
    canonicalization_processor = FakeCanonicalizationBarrierProcessor(
        outcomes=["canonicalized"]
    )
    registry_processor = FakeRegistryProcessor(outcomes=["no_work"])

    service = FaqWorkbenchParallelProcessingCoordinatorService(
        section_processor=section_processor,
        canonicalization_barrier_processor=canonicalization_processor,
        registry_processor=registry_processor,
    )

    result = await service.run_parallel_processing(
        RunParallelWorkbenchProcessingCommand(
            project_id="project-1",
            document_id="document-1",
            processing_run_id="processing-run-1",
            section_worker_count=2,
            worker_id_prefix="worker",
            max_cycles=1,
        )
    )

    assert result.cycle_count == 1
    assert result.cycles[0].section_worker_outcomes == ("no_work", "no_work")
    assert result.cycles[0].canonicalization_barrier_outcomes == ("canonicalized",)
    assert result.cycles[0].registry_writer_outcomes == ("no_work",)
    assert result.canonicalization_count == 1

    assert len(canonicalization_processor.commands) == 1
    assert canonicalization_processor.commands[0] == (
        ProcessParallelCanonicalizationBarrierCommand(
            project_id="project-1",
            document_id="document-1",
            processing_run_id="processing-run-1",
            worker_id="worker-canonicalization-1",
            lease_seconds=300,
        )
    )


@pytest.mark.asyncio
async def test_parallel_processing_blocks_canonicalization_barrier_while_section_wave_makes_progress() -> None:
    section_processor = FakeSectionProcessor(outcomes=["claim_observations_persisted"])
    canonicalization_processor = FakeCanonicalizationBarrierProcessor(
        outcomes=["canonicalized"]
    )
    registry_processor = FakeRegistryProcessor(outcomes=["no_work"])

    service = FaqWorkbenchParallelProcessingCoordinatorService(
        section_processor=section_processor,
        canonicalization_barrier_processor=canonicalization_processor,
        registry_processor=registry_processor,
    )

    result = await service.run_parallel_processing(
        RunParallelWorkbenchProcessingCommand(
            project_id="project-1",
            document_id="document-1",
            processing_run_id="processing-run-1",
            section_worker_count=1,
            max_cycles=1,
        )
    )

    assert result.cycles[0].section_worker_outcomes == (
        "claim_observations_persisted",
    )
    assert result.cycles[0].canonicalization_barrier_outcomes == (
        "blocked_by_sections",
    )
    assert not canonicalization_processor.commands
    assert result.canonicalization_count == 0


@pytest.mark.asyncio
async def test_parallel_processing_keeps_backward_compatible_empty_barrier_when_not_wired_yet() -> None:
    section_processor = FakeSectionProcessor(outcomes=["no_work"])
    registry_processor = FakeRegistryProcessor(outcomes=["no_work"])

    service = FaqWorkbenchParallelProcessingCoordinatorService(
        section_processor=section_processor,
        registry_processor=registry_processor,
    )

    result = await service.run_parallel_processing(
        RunParallelWorkbenchProcessingCommand(
            project_id="project-1",
            document_id="document-1",
            processing_run_id="processing-run-1",
            section_worker_count=1,
            max_cycles=1,
        )
    )

    assert result.cycles[0].canonicalization_barrier_outcomes == ()
    assert result.canonicalization_count == 0
    assert result.completed_without_work_left is True


@pytest.mark.asyncio
async def test_parallel_processing_treats_canonicalization_no_work_as_no_progress() -> None:
    section_processor = FakeSectionProcessor(outcomes=["no_work"])
    canonicalization_processor = FakeCanonicalizationBarrierProcessor(
        outcomes=["no_work"]
    )
    registry_processor = FakeRegistryProcessor(outcomes=["no_work"])

    service = FaqWorkbenchParallelProcessingCoordinatorService(
        section_processor=section_processor,
        canonicalization_barrier_processor=canonicalization_processor,
        registry_processor=registry_processor,
    )

    result = await service.run_parallel_processing(
        RunParallelWorkbenchProcessingCommand(
            project_id="project-1",
            document_id="document-1",
            processing_run_id="processing-run-1",
            section_worker_count=1,
            max_cycles=2,
        )
    )

    assert result.cycle_count == 1
    assert result.cycles[0].made_progress is False
    assert result.completed_without_work_left is True


def test_parallel_canonicalization_barrier_command_validates_required_fields() -> None:
    with pytest.raises(Exception, match="project_id"):
        ProcessParallelCanonicalizationBarrierCommand(
            project_id="",
            document_id="document-1",
            processing_run_id="processing-run-1",
            worker_id="worker",
        )

    with pytest.raises(Exception, match="document_id"):
        ProcessParallelCanonicalizationBarrierCommand(
            project_id="project-1",
            document_id="",
            processing_run_id="processing-run-1",
            worker_id="worker",
        )

    with pytest.raises(Exception, match="processing_run_id"):
        ProcessParallelCanonicalizationBarrierCommand(
            project_id="project-1",
            document_id="document-1",
            processing_run_id="",
            worker_id="worker",
        )

    with pytest.raises(Exception, match="worker_id"):
        ProcessParallelCanonicalizationBarrierCommand(
            project_id="project-1",
            document_id="document-1",
            processing_run_id="processing-run-1",
            worker_id="",
        )

    with pytest.raises(Exception, match="lease_seconds"):
        ProcessParallelCanonicalizationBarrierCommand(
            project_id="project-1",
            document_id="document-1",
            processing_run_id="processing-run-1",
            worker_id="worker",
            lease_seconds=0,
        )
@pytest.mark.asyncio
async def test_parallel_processing_uses_durable_drain_counts_before_canonicalization_barrier() -> None:
    section_processor = FakeSectionProcessor(outcomes=["no_work", "no_work"])
    canonicalization_processor = FakeCanonicalizationBarrierProcessor(
        outcomes=["canonicalized"]
    )
    registry_processor = FakeRegistryProcessor(outcomes=["no_work"])
    drain_counts_provider = FakeDrainCountsProvider(counts=[ParallelDrainWorkCounts()])

    service = FaqWorkbenchParallelProcessingCoordinatorService(
        section_processor=section_processor,
        canonicalization_barrier_processor=canonicalization_processor,
        registry_processor=registry_processor,
        drain_counts_provider=drain_counts_provider,
    )

    result = await service.run_parallel_processing(
        RunParallelWorkbenchProcessingCommand(
            project_id="project-1",
            document_id="document-1",
            processing_run_id="processing-run-1",
            section_worker_count=2,
            max_cycles=1,
        )
    )

    assert result.cycles[0].canonicalization_barrier_outcomes == ("canonicalized",)
    assert len(canonicalization_processor.commands) == 1
    assert drain_counts_provider.calls == [
        {
            "project_id": "project-1",
            "document_id": "document-1",
            "processing_run_id": "processing-run-1",
        }
    ]


@pytest.mark.asyncio
async def test_parallel_processing_blocks_canonicalization_when_durable_section_work_remains() -> None:
    section_processor = FakeSectionProcessor(outcomes=["no_work"])
    canonicalization_processor = FakeCanonicalizationBarrierProcessor(
        outcomes=["canonicalized"]
    )
    registry_processor = FakeRegistryProcessor(outcomes=["no_work"])
    drain_counts_provider = FakeDrainCountsProvider(
        counts=[ParallelDrainWorkCounts(section_ready=1)]
    )

    service = FaqWorkbenchParallelProcessingCoordinatorService(
        section_processor=section_processor,
        canonicalization_barrier_processor=canonicalization_processor,
        registry_processor=registry_processor,
        drain_counts_provider=drain_counts_provider,
    )

    result = await service.run_parallel_processing(
        RunParallelWorkbenchProcessingCommand(
            project_id="project-1",
            document_id="document-1",
            processing_run_id="processing-run-1",
            section_worker_count=1,
            max_cycles=1,
        )
    )

    assert result.cycles[0].canonicalization_barrier_outcomes == ("keep_draining",)
    assert not canonicalization_processor.commands
    assert result.cycles[0].made_progress is False


@pytest.mark.asyncio
async def test_parallel_processing_blocks_canonicalization_when_durable_leases_remain() -> None:
    section_processor = FakeSectionProcessor(outcomes=["no_work"])
    canonicalization_processor = FakeCanonicalizationBarrierProcessor(
        outcomes=["canonicalized"]
    )
    registry_processor = FakeRegistryProcessor(outcomes=["no_work"])
    drain_counts_provider = FakeDrainCountsProvider(
        counts=[ParallelDrainWorkCounts(section_leased=1)]
    )

    service = FaqWorkbenchParallelProcessingCoordinatorService(
        section_processor=section_processor,
        canonicalization_barrier_processor=canonicalization_processor,
        registry_processor=registry_processor,
        drain_counts_provider=drain_counts_provider,
    )

    result = await service.run_parallel_processing(
        RunParallelWorkbenchProcessingCommand(
            project_id="project-1",
            document_id="document-1",
            processing_run_id="processing-run-1",
            section_worker_count=1,
            max_cycles=1,
        )
    )

    assert result.cycles[0].canonicalization_barrier_outcomes == ("blocked_by_leases",)
    assert not canonicalization_processor.commands


@pytest.mark.asyncio
async def test_parallel_processing_blocks_canonicalization_when_durable_failures_remain() -> None:
    section_processor = FakeSectionProcessor(outcomes=["no_work"])
    canonicalization_processor = FakeCanonicalizationBarrierProcessor(
        outcomes=["canonicalized"]
    )
    registry_processor = FakeRegistryProcessor(outcomes=["no_work"])
    drain_counts_provider = FakeDrainCountsProvider(
        counts=[ParallelDrainWorkCounts(section_failed=1)]
    )

    service = FaqWorkbenchParallelProcessingCoordinatorService(
        section_processor=section_processor,
        canonicalization_barrier_processor=canonicalization_processor,
        registry_processor=registry_processor,
        drain_counts_provider=drain_counts_provider,
    )

    result = await service.run_parallel_processing(
        RunParallelWorkbenchProcessingCommand(
            project_id="project-1",
            document_id="document-1",
            processing_run_id="processing-run-1",
            section_worker_count=1,
            max_cycles=1,
        )
    )

    assert result.cycles[0].canonicalization_barrier_outcomes == ("failed",)
    assert not canonicalization_processor.commands

@pytest.mark.asyncio
async def test_parallel_processing_marks_lifecycle_completed_after_terminal_success_cycle() -> None:
    section_processor = FakeSectionProcessor(outcomes=["no_work"])
    canonicalization_processor = FakeCanonicalizationBarrierProcessor(
        outcomes=["already_canonicalized"]
    )
    registry_processor = FakeRegistryProcessor(outcomes=["no_work"])
    drain_counts_provider = FakeDrainCountsProvider(counts=[ParallelDrainWorkCounts()])
    lifecycle_completion = FakeLifecycleCompletionPort()

    service = FaqWorkbenchParallelProcessingCoordinatorService(
        section_processor=section_processor,
        canonicalization_barrier_processor=canonicalization_processor,
        registry_processor=registry_processor,
        drain_counts_provider=drain_counts_provider,
        lifecycle_completion_port=lifecycle_completion,
    )

    result = await service.run_parallel_processing(
        RunParallelWorkbenchProcessingCommand(
            project_id="project-1",
            document_id="document-1",
            processing_run_id="processing-run-1",
            section_worker_count=1,
            max_cycles=1,
        )
    )

    assert result.completed_without_work_left is True
    assert lifecycle_completion.calls == [
        {
            "project_id": "project-1",
            "document_id": "document-1",
            "processing_run_id": "processing-run-1",
        }
    ]


@pytest.mark.asyncio
async def test_parallel_processing_does_not_mark_lifecycle_completed_when_barrier_is_blocked() -> None:
    section_processor = FakeSectionProcessor(outcomes=["no_work"])
    canonicalization_processor = FakeCanonicalizationBarrierProcessor(
        outcomes=["canonicalized"]
    )
    registry_processor = FakeRegistryProcessor(outcomes=["no_work"])
    drain_counts_provider = FakeDrainCountsProvider(
        counts=[ParallelDrainWorkCounts(section_ready=1)]
    )
    lifecycle_completion = FakeLifecycleCompletionPort()

    service = FaqWorkbenchParallelProcessingCoordinatorService(
        section_processor=section_processor,
        canonicalization_barrier_processor=canonicalization_processor,
        registry_processor=registry_processor,
        drain_counts_provider=drain_counts_provider,
        lifecycle_completion_port=lifecycle_completion,
    )

    result = await service.run_parallel_processing(
        RunParallelWorkbenchProcessingCommand(
            project_id="project-1",
            document_id="document-1",
            processing_run_id="processing-run-1",
            section_worker_count=1,
            max_cycles=1,
        )
    )

    assert result.completed_without_work_left is True
    assert result.cycles[0].canonicalization_barrier_outcomes == ("keep_draining",)
    assert lifecycle_completion.calls == []


@pytest.mark.asyncio
async def test_parallel_processing_does_not_mark_lifecycle_completed_on_wait_for_snapshot() -> None:
    section_processor = FakeSectionProcessor(outcomes=["no_work"])
    canonicalization_processor = FakeCanonicalizationBarrierProcessor(
        outcomes=["already_canonicalized"]
    )
    registry_processor = FakeRegistryProcessor(outcomes=["wait_for_snapshot"])
    drain_counts_provider = FakeDrainCountsProvider(counts=[ParallelDrainWorkCounts()])
    lifecycle_completion = FakeLifecycleCompletionPort()

    service = FaqWorkbenchParallelProcessingCoordinatorService(
        section_processor=section_processor,
        canonicalization_barrier_processor=canonicalization_processor,
        registry_processor=registry_processor,
        drain_counts_provider=drain_counts_provider,
        lifecycle_completion_port=lifecycle_completion,
    )

    await service.run_parallel_processing(
        RunParallelWorkbenchProcessingCommand(
            project_id="project-1",
            document_id="document-1",
            processing_run_id="processing-run-1",
            section_worker_count=1,
            max_cycles=1,
        )
    )

    assert lifecycle_completion.calls == []

@pytest.mark.asyncio
async def test_parallel_processing_treats_already_canonicalized_as_no_progress_for_completion() -> None:
    section_processor = FakeSectionProcessor(outcomes=["no_work"])
    canonicalization_processor = FakeCanonicalizationBarrierProcessor(
        outcomes=["already_canonicalized"]
    )
    registry_processor = FakeRegistryProcessor(outcomes=["no_work"])
    drain_counts_provider = FakeDrainCountsProvider(counts=[ParallelDrainWorkCounts()])
    lifecycle_completion = FakeLifecycleCompletionPort()

    service = FaqWorkbenchParallelProcessingCoordinatorService(
        section_processor=section_processor,
        canonicalization_barrier_processor=canonicalization_processor,
        registry_processor=registry_processor,
        drain_counts_provider=drain_counts_provider,
        lifecycle_completion_port=lifecycle_completion,
    )

    result = await service.run_parallel_processing(
        RunParallelWorkbenchProcessingCommand(
            project_id="project-1",
            document_id="document-1",
            processing_run_id="processing-run-1",
            section_worker_count=1,
            max_cycles=1,
        )
    )

    assert result.completed_without_work_left is True
    assert result.canonicalization_count == 0
    assert lifecycle_completion.calls == [
        {
            "project_id": "project-1",
            "document_id": "document-1",
            "processing_run_id": "processing-run-1",
        }
    ]

def test_parallel_processing_outcome_made_progress_treats_already_canonicalized_as_no_progress() -> None:
    from src.application.services import faq_workbench_parallel_processing_coordinator_service as module

    assert module._outcome_made_progress("already_canonicalized") is False
    assert module._outcome_made_progress("canonicalized") is True

def test_parallel_processing_run_loop_calls_success_lifecycle_before_terminal_break() -> None:
    from pathlib import Path

    source = Path(
        "src/application/services/faq_workbench_parallel_processing_coordinator_service.py"
    ).read_text(encoding="utf-8")
    run_loop = source.split("async def run_parallel_processing", 1)[1].split(
        "async def _mark_success_lifecycle_if_terminal",
        1,
    )[0]

    assert "if not cycle.made_progress:" in run_loop
    assert "await self._mark_success_lifecycle_if_terminal(" in run_loop
    assert run_loop.index("await self._mark_success_lifecycle_if_terminal(") < run_loop.index("break")

def test_parallel_processing_terminal_success_accepts_already_canonicalized() -> None:
    from src.application.services.faq_workbench_parallel_processing_coordinator_service import (
        ParallelWorkbenchProcessingCycle,
        _cycle_is_terminal_success,
    )

    cycle = ParallelWorkbenchProcessingCycle(
        cycle_index=0,
        section_worker_outcomes=("no_work",),
        canonicalization_barrier_outcomes=("already_canonicalized",),
        registry_writer_outcomes=("no_work",),
    )

    assert cycle.made_progress is False
    assert _cycle_is_terminal_success(cycle) is True
