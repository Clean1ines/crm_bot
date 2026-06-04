from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol

from src.domain.project_plane.knowledge_workbench import (
    DomainInvariantError,
    ParallelDrainWorkCounts,
    ParallelProcessingIntegrityCounts,
    decide_parallel_canonicalization_readiness,
    decide_parallel_finalization,
)


class SectionWorkItemProcessorPort(Protocol):
    async def process_next_section_work_item(
        self,
        command: ProcessParallelSectionWorkItemCommand,
    ) -> object: ...


class RegistryApplicationWorkItemProcessorPort(Protocol):
    async def process_next_registry_application_work_item(
        self,
        command: ProcessParallelRegistryApplicationWorkItemCommand,
    ) -> object: ...


class CanonicalizationBarrierProcessorPort(Protocol):
    async def process_document_canonicalization_barrier(
        self,
        command: ProcessParallelCanonicalizationBarrierCommand,
    ) -> object: ...


@dataclass(frozen=True, slots=True)
class ParallelProcessingIntegrityError(RuntimeError):
    project_id: str
    document_id: str
    processing_run_id: str
    document_sections_total: int
    section_queue_items_total: int
    claim_observation_artifacts_total: int
    canonicalization_artifacts_total: int

    def __str__(self) -> str:
        return (
            "Parallel Workbench integrity violation for document "
            f"{self.document_id} / run {self.processing_run_id}: "
            f"document_sections_total={self.document_sections_total}, "
            f"section_queue_items_total={self.section_queue_items_total}, "
            f"claim_observation_artifacts_total={self.claim_observation_artifacts_total}, "
            f"canonicalization_artifacts_total={self.canonicalization_artifacts_total}"
        )


class ParallelDrainCountsProviderPort(Protocol):
    async def get_parallel_processing_drain_counts(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
    ) -> ParallelDrainWorkCounts: ...


class ParallelProcessingIntegrityCountsProviderPort(Protocol):
    async def get_parallel_processing_integrity_counts(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
    ) -> ParallelProcessingIntegrityCounts: ...


class ParallelProcessingLifecycleCompletionPort(Protocol):
    async def mark_parallel_processing_completed(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class ProcessParallelSectionWorkItemCommand:
    project_id: str
    document_id: str
    processing_run_id: str
    worker_id: str
    lease_seconds: int = 300

    def __post_init__(self) -> None:
        if not self.project_id:
            raise DomainInvariantError("parallel section work requires project_id")
        if not self.document_id:
            raise DomainInvariantError("parallel section work requires document_id")
        if not self.processing_run_id:
            raise DomainInvariantError(
                "parallel section work requires processing_run_id"
            )
        if not self.worker_id:
            raise DomainInvariantError("parallel section work requires worker_id")
        if self.lease_seconds < 1:
            raise DomainInvariantError(
                "parallel section work lease_seconds must be positive"
            )


@dataclass(frozen=True, slots=True)
class ProcessParallelCanonicalizationBarrierCommand:
    project_id: str
    document_id: str
    processing_run_id: str
    worker_id: str
    lease_seconds: int = 300

    def __post_init__(self) -> None:
        if not self.project_id:
            raise DomainInvariantError(
                "parallel canonicalization barrier requires project_id"
            )
        if not self.document_id:
            raise DomainInvariantError(
                "parallel canonicalization barrier requires document_id"
            )
        if not self.processing_run_id:
            raise DomainInvariantError(
                "parallel canonicalization barrier requires processing_run_id"
            )
        if not self.worker_id:
            raise DomainInvariantError(
                "parallel canonicalization barrier requires worker_id"
            )
        if self.lease_seconds < 1:
            raise DomainInvariantError(
                "parallel canonicalization barrier lease_seconds must be positive"
            )


@dataclass(frozen=True, slots=True)
class ProcessParallelRegistryApplicationWorkItemCommand:
    project_id: str
    document_id: str
    processing_run_id: str
    worker_id: str
    lease_seconds: int = 300

    def __post_init__(self) -> None:
        if not self.project_id:
            raise DomainInvariantError("parallel registry work requires project_id")
        if not self.document_id:
            raise DomainInvariantError("parallel registry work requires document_id")
        if not self.processing_run_id:
            raise DomainInvariantError(
                "parallel registry work requires processing_run_id"
            )
        if not self.worker_id:
            raise DomainInvariantError("parallel registry work requires worker_id")
        if self.lease_seconds < 1:
            raise DomainInvariantError(
                "parallel registry work lease_seconds must be positive"
            )


@dataclass(frozen=True, slots=True)
class RunParallelWorkbenchProcessingCommand:
    project_id: str
    document_id: str
    processing_run_id: str
    section_worker_count: int = 3
    worker_id_prefix: str = "workbench"
    lease_seconds: int = 300
    max_cycles: int = 10_000
    max_registry_drain_steps_per_cycle: int = 10_000

    def __post_init__(self) -> None:
        if not self.project_id:
            raise DomainInvariantError("parallel processing requires project_id")
        if not self.document_id:
            raise DomainInvariantError("parallel processing requires document_id")
        if not self.processing_run_id:
            raise DomainInvariantError("parallel processing requires processing_run_id")
        if self.section_worker_count < 1:
            raise DomainInvariantError(
                "parallel processing section_worker_count must be positive"
            )
        if not self.worker_id_prefix:
            raise DomainInvariantError("parallel processing requires worker_id_prefix")
        if self.lease_seconds < 1:
            raise DomainInvariantError(
                "parallel processing lease_seconds must be positive"
            )
        if self.max_cycles < 1:
            raise DomainInvariantError(
                "parallel processing max_cycles must be positive"
            )
        if self.max_registry_drain_steps_per_cycle < 1:
            raise DomainInvariantError(
                "parallel processing registry drain limit must be positive"
            )


@dataclass(frozen=True, slots=True)
class ParallelWorkbenchProcessingCycle:
    cycle_index: int
    section_worker_outcomes: tuple[str, ...]
    canonicalization_barrier_outcomes: tuple[str, ...]
    registry_writer_outcomes: tuple[str, ...]

    @property
    def made_progress(self) -> bool:
        return (
            any(
                _outcome_made_progress(outcome)
                for outcome in self.section_worker_outcomes
            )
            or any(
                _outcome_made_progress(outcome)
                for outcome in self.canonicalization_barrier_outcomes
            )
            or any(
                _outcome_made_progress(outcome)
                for outcome in self.registry_writer_outcomes
            )
        )

    @property
    def section_claim_count(self) -> int:
        return sum(
            1
            for outcome in self.section_worker_outcomes
            if outcome not in {"no_work", "skip_terminal"}
        )

    @property
    def canonicalization_count(self) -> int:
        return sum(
            1
            for outcome in self.canonicalization_barrier_outcomes
            if outcome
            not in {
                "no_work",
                "skip_terminal",
                "blocked_by_sections",
                "already_canonicalized",
            }
        )

    @property
    def registry_apply_count(self) -> int:
        return sum(
            1 for outcome in self.registry_writer_outcomes if outcome == "applied"
        )


@dataclass(frozen=True, slots=True)
class RunParallelWorkbenchProcessingResult:
    cycles: tuple[ParallelWorkbenchProcessingCycle, ...]

    @property
    def cycle_count(self) -> int:
        return len(self.cycles)

    @property
    def section_claim_count(self) -> int:
        return sum(cycle.section_claim_count for cycle in self.cycles)

    @property
    def canonicalization_count(self) -> int:
        return sum(cycle.canonicalization_count for cycle in self.cycles)

    @property
    def registry_apply_count(self) -> int:
        return sum(cycle.registry_apply_count for cycle in self.cycles)

    @property
    def completed_without_work_left(self) -> bool:
        if not self.cycles:
            return True
        return not self.cycles[-1].made_progress


class FaqWorkbenchParallelProcessingCoordinatorService:
    def __init__(
        self,
        *,
        section_processor: SectionWorkItemProcessorPort,
        registry_processor: RegistryApplicationWorkItemProcessorPort,
        canonicalization_barrier_processor: CanonicalizationBarrierProcessorPort
        | None = None,
        drain_counts_provider: ParallelDrainCountsProviderPort | None = None,
        integrity_counts_provider: ParallelProcessingIntegrityCountsProviderPort
        | None = None,
        lifecycle_completion_port: ParallelProcessingLifecycleCompletionPort
        | None = None,
    ) -> None:
        self._section_processor = section_processor
        self._registry_processor = registry_processor
        self._canonicalization_barrier_processor = canonicalization_barrier_processor
        self._drain_counts_provider = drain_counts_provider
        self._integrity_counts_provider = integrity_counts_provider
        self._lifecycle_completion_port = lifecycle_completion_port

    async def run_parallel_processing(
        self,
        command: RunParallelWorkbenchProcessingCommand,
    ) -> RunParallelWorkbenchProcessingResult:
        cycles: list[ParallelWorkbenchProcessingCycle] = []

        for cycle_index in range(command.max_cycles):
            section_outcomes = await self._run_section_worker_wave(
                command=command,
                cycle_index=cycle_index,
            )
            canonicalization_outcomes = await self._run_canonicalization_barrier(
                command=command,
                cycle_index=cycle_index,
                section_outcomes=section_outcomes,
            )
            registry_outcomes = await self._drain_registry_writer(
                command=command,
                cycle_index=cycle_index,
            )

            cycle = ParallelWorkbenchProcessingCycle(
                cycle_index=cycle_index,
                section_worker_outcomes=section_outcomes,
                canonicalization_barrier_outcomes=canonicalization_outcomes,
                registry_writer_outcomes=registry_outcomes,
            )
            cycles.append(cycle)

            if not cycle.made_progress:
                await self._assert_parallel_processing_integrity(command)
                await self._mark_success_lifecycle_if_terminal(
                    command=command,
                    cycle=cycle,
                )
                break

        return RunParallelWorkbenchProcessingResult(cycles=tuple(cycles))

    async def _mark_success_lifecycle_if_terminal(
        self,
        *,
        command: RunParallelWorkbenchProcessingCommand,
        cycle: ParallelWorkbenchProcessingCycle,
    ) -> None:
        if self._lifecycle_completion_port is None:
            return
        if not _cycle_is_terminal_success(cycle):
            return
        await self._assert_parallel_processing_integrity(command)
        await self._lifecycle_completion_port.mark_parallel_processing_completed(
            project_id=command.project_id,
            document_id=command.document_id,
            processing_run_id=command.processing_run_id,
        )

    async def _assert_parallel_processing_integrity(
        self,
        command: RunParallelWorkbenchProcessingCommand,
    ) -> None:
        if self._integrity_counts_provider is None:
            return

        counts = await self._integrity_counts_provider.get_parallel_processing_integrity_counts(
            project_id=command.project_id,
            document_id=command.document_id,
            processing_run_id=command.processing_run_id,
        )

        if (
            counts.document_sections_total > 0
            and counts.section_queue_items_total != counts.document_sections_total
        ):
            raise ParallelProcessingIntegrityError(
                project_id=command.project_id,
                document_id=command.document_id,
                processing_run_id=command.processing_run_id,
                document_sections_total=counts.document_sections_total,
                section_queue_items_total=counts.section_queue_items_total,
                claim_observation_artifacts_total=counts.claim_observation_artifacts_total,
                canonicalization_artifacts_total=counts.canonicalization_artifacts_total,
            )

    async def _run_section_worker_wave(
        self,
        *,
        command: RunParallelWorkbenchProcessingCommand,
        cycle_index: int,
    ) -> tuple[str, ...]:
        worker_commands = tuple(
            ProcessParallelSectionWorkItemCommand(
                project_id=command.project_id,
                document_id=command.document_id,
                processing_run_id=command.processing_run_id,
                worker_id=(
                    f"{command.worker_id_prefix}-section-"
                    f"{cycle_index + 1}-{worker_index + 1}"
                ),
                lease_seconds=command.lease_seconds,
            )
            for worker_index in range(command.section_worker_count)
        )

        results = await asyncio.gather(
            *(
                self._section_processor.process_next_section_work_item(worker_command)
                for worker_command in worker_commands
            )
        )
        return tuple(_outcome_value(result) for result in results)

    async def _run_canonicalization_barrier(
        self,
        *,
        command: RunParallelWorkbenchProcessingCommand,
        cycle_index: int,
        section_outcomes: tuple[str, ...],
    ) -> tuple[str, ...]:
        if self._canonicalization_barrier_processor is None:
            return ()

        readiness_outcome = await self._canonicalization_barrier_readiness_outcome(
            command=command,
            section_outcomes=section_outcomes,
        )
        if readiness_outcome != "can_finalize":
            return (readiness_outcome,)

        result = await self._canonicalization_barrier_processor.process_document_canonicalization_barrier(
            ProcessParallelCanonicalizationBarrierCommand(
                project_id=command.project_id,
                document_id=command.document_id,
                processing_run_id=command.processing_run_id,
                worker_id=f"{command.worker_id_prefix}-canonicalization-{cycle_index + 1}",
                lease_seconds=command.lease_seconds,
            )
        )
        return (_outcome_value(result),)

    async def _canonicalization_barrier_readiness_outcome(
        self,
        *,
        command: RunParallelWorkbenchProcessingCommand,
        section_outcomes: tuple[str, ...],
    ) -> str:
        if self._drain_counts_provider is None:
            return (
                "can_finalize"
                if _section_wave_is_drained(section_outcomes)
                else "blocked_by_sections"
            )

        counts = await self._drain_counts_provider.get_parallel_processing_drain_counts(
            project_id=command.project_id,
            document_id=command.document_id,
            processing_run_id=command.processing_run_id,
        )
        if self._integrity_counts_provider is None:
            readiness = decide_parallel_finalization(counts)
            return readiness.decision.value

        integrity = (
            await self._integrity_counts_provider.get_parallel_processing_integrity_counts(
                project_id=command.project_id,
                document_id=command.document_id,
                processing_run_id=command.processing_run_id,
            )
        )
        readiness = decide_parallel_canonicalization_readiness(
            counts=counts,
            integrity=integrity,
        )
        return readiness.decision.value

    async def _drain_registry_writer(
        self,
        *,
        command: RunParallelWorkbenchProcessingCommand,
        cycle_index: int,
    ) -> tuple[str, ...]:
        outcomes: list[str] = []

        for step_index in range(command.max_registry_drain_steps_per_cycle):
            result = await self._registry_processor.process_next_registry_application_work_item(
                ProcessParallelRegistryApplicationWorkItemCommand(
                    project_id=command.project_id,
                    document_id=command.document_id,
                    processing_run_id=command.processing_run_id,
                    worker_id=(
                        f"{command.worker_id_prefix}-registry-"
                        f"{cycle_index + 1}-{step_index + 1}"
                    ),
                    lease_seconds=command.lease_seconds,
                )
            )
            outcome = _outcome_value(result)
            outcomes.append(outcome)

            if outcome == "no_work":
                break

            if outcome in {"wait_for_snapshot", "skip_terminal"}:
                break

        return tuple(outcomes)


def _cycle_is_terminal_success(cycle: ParallelWorkbenchProcessingCycle) -> bool:
    if cycle.made_progress:
        return False
    if not cycle.section_worker_outcomes:
        return False
    if not cycle.canonicalization_barrier_outcomes:
        return False
    if not cycle.registry_writer_outcomes:
        return False

    forbidden_outcomes = {
        "blocked_by_sections",
        "blocked_by_leases",
        "waiting_for_fresh_registry",
        "wait_for_snapshot",
        "keep_draining",
        "failed",
    }
    all_outcomes = (
        cycle.section_worker_outcomes
        + cycle.canonicalization_barrier_outcomes
        + cycle.registry_writer_outcomes
    )
    return not any(outcome in forbidden_outcomes for outcome in all_outcomes)


def _section_wave_is_drained(outcomes: tuple[str, ...]) -> bool:
    return bool(outcomes) and all(
        outcome in {"no_work", "skip_terminal"} for outcome in outcomes
    )


def _outcome_value(result: object) -> str:
    outcome = getattr(result, "outcome", result)
    value = getattr(outcome, "value", outcome)
    return str(value)


def _outcome_made_progress(outcome: str) -> bool:
    return outcome not in {
        "no_work",
        "skip_terminal",
        "wait_for_snapshot",
        "blocked_by_sections",
        "blocked_by_leases",
        "already_canonicalized",
        "waiting_for_fresh_registry",
        "keep_draining",
        "failed",
    }


__all__ = [
    "CanonicalizationBarrierProcessorPort",
    "FaqWorkbenchParallelProcessingCoordinatorService",
    "ParallelDrainCountsProviderPort",
    "ParallelProcessingIntegrityCounts",
    "ParallelProcessingIntegrityCountsProviderPort",
    "ParallelProcessingIntegrityError",
    "ParallelProcessingLifecycleCompletionPort",
    "ParallelWorkbenchProcessingCycle",
    "ProcessParallelCanonicalizationBarrierCommand",
    "ProcessParallelRegistryApplicationWorkItemCommand",
    "ProcessParallelSectionWorkItemCommand",
    "RegistryApplicationWorkItemProcessorPort",
    "RunParallelWorkbenchProcessingCommand",
    "RunParallelWorkbenchProcessingResult",
    "SectionWorkItemProcessorPort",
]
