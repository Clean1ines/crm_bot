from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timezone
from typing import Protocol, cast
from uuid import uuid4

from src.application.ports.faq_workbench_claim_observations_generator import (
    FaqWorkbenchClaimObservationsGeneratorPort,
)
from src.application.ports.knowledge_workbench import (
    KnowledgeWorkbenchClaimObservationsRepositoryPort,
)
from src.application.ports.llm_json_invocation import LlmJsonInvocationPort
from src.application.services.faq_workbench_claim_observations_service import (
    FaqWorkbenchClaimObservationsService,
    ProcessClaimObservationsCommand,
    ProcessClaimObservationsGenerationErrorCommand,
)
from src.application.services.faq_workbench_section_work_item_processor_service import (
    ProcessLeasedClaimObservationsCommand,
    ProcessLeasedClaimObservationsResult,
)
from src.infrastructure.llm.faq_workbench_claim_observations_generator import (
    FaqWorkbenchClaimObservationsGenerator,
    FaqWorkbenchClaimObservationsGeneratorConfig,
)
from src.infrastructure.llm.workbench_qwen_json_invocation import (
    WorkbenchPromptAFallbackLlmJsonInvocationAdapter,
    workbench_qwen_worker_context,
)
from src.application.services.faq_workbench_parallel_processing_coordinator_service import (
    FaqWorkbenchParallelProcessingCoordinatorService,
    RunParallelWorkbenchProcessingCommand,
)
from src.domain.project_plane.llm_routing import LlmJsonInvocationResult
from src.domain.project_plane.knowledge_workbench import (
    DomainInvariantError,
    FactRegistry,
    RegistrySnapshot,
)
from src.infrastructure.queue.job_exceptions import (
    PermanentJobError,
    TransientJobError,
)
from src.infrastructure.db.knowledge_workbench_repository import (
    KnowledgeWorkbenchRepository,
)
from src.interfaces.composition.faq_workbench_parallel_processing import (
    FaqWorkbenchParallelProcessingDependencies,
    make_workbench_canonicalization_barrier_service_from_repository,
    make_workbench_parallel_processing_coordinator_from_repository,
)


PARALLEL_WORKBENCH_PROCESSING_TASK_TYPE = "process_workbench_parallel_processing"


class IdFactory(Protocol):
    def new_id(self, prefix: str) -> str: ...


class TimeProvider(Protocol):
    def now(self) -> datetime: ...


class ClaimObservationsRunnerRepositoryPort(
    KnowledgeWorkbenchClaimObservationsRepositoryPort,
    Protocol,
):
    async def get_fact_registry_for_run(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
    ) -> FactRegistry | None: ...

    async def get_latest_registry_snapshot(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
    ) -> RegistrySnapshot | None: ...


def _workbench_repository(connection: object) -> KnowledgeWorkbenchRepository:
    repository_factory = cast(
        Callable[[object], KnowledgeWorkbenchRepository],
        KnowledgeWorkbenchRepository,
    )
    return repository_factory(connection)


class ParallelWorkbenchProcessingCoordinatorPort(Protocol):
    async def run_parallel_processing(
        self,
        command: RunParallelWorkbenchProcessingCommand,
    ) -> object: ...


@dataclass(frozen=True, slots=True)
class WorkbenchParallelProcessingJobPayloadDto:
    project_id: str
    document_id: str
    processing_run_id: str
    section_worker_count: int = 4
    worker_id_prefix: str = "workbench-parallel"
    lease_seconds: int = 300
    max_cycles: int = 10_000
    max_registry_drain_steps_per_cycle: int = 10_000

    def __post_init__(self) -> None:
        if not self.project_id:
            raise DomainInvariantError("parallel queue payload requires project_id")
        if not self.document_id:
            raise DomainInvariantError("parallel queue payload requires document_id")
        if not self.processing_run_id:
            raise DomainInvariantError(
                "parallel queue payload requires processing_run_id"
            )
        if self.section_worker_count < 1:
            raise DomainInvariantError(
                "parallel queue payload section_worker_count must be positive"
            )
        if not self.worker_id_prefix:
            raise DomainInvariantError(
                "parallel queue payload requires worker_id_prefix"
            )
        if self.lease_seconds < 1:
            raise DomainInvariantError(
                "parallel queue payload lease_seconds must be positive"
            )
        if self.max_cycles < 1:
            raise DomainInvariantError(
                "parallel queue payload max_cycles must be positive"
            )
        if self.max_registry_drain_steps_per_cycle < 1:
            raise DomainInvariantError(
                "parallel queue payload registry drain limit must be positive"
            )

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, object],
    ) -> WorkbenchParallelProcessingJobPayloadDto:
        return cls(
            project_id=_required_text(payload, "project_id"),
            document_id=_required_text(payload, "document_id"),
            processing_run_id=_required_text(payload, "processing_run_id"),
            section_worker_count=_positive_int(
                payload,
                "section_worker_count",
                default=4,
            ),
            worker_id_prefix=_optional_text(
                payload,
                "worker_id_prefix",
                default="workbench-parallel",
            ),
            lease_seconds=_positive_int(payload, "lease_seconds", default=300),
            max_cycles=_positive_int(payload, "max_cycles", default=10_000),
            max_registry_drain_steps_per_cycle=_positive_int(
                payload,
                "max_registry_drain_steps_per_cycle",
                default=10_000,
            ),
        )

    def to_command(self) -> RunParallelWorkbenchProcessingCommand:
        return RunParallelWorkbenchProcessingCommand(
            project_id=self.project_id,
            document_id=self.document_id,
            processing_run_id=self.processing_run_id,
            section_worker_count=self.section_worker_count,
            worker_id_prefix=self.worker_id_prefix,
            lease_seconds=self.lease_seconds,
            max_cycles=self.max_cycles,
            max_registry_drain_steps_per_cycle=(
                self.max_registry_drain_steps_per_cycle
            ),
        )


class UuidWorkbenchIdFactory:
    def new_id(self, prefix: str) -> str:
        return f"{prefix}-{uuid4()}"


class SystemWorkbenchTimeProvider:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


async def handle_workbench_parallel_processing_job(
    *,
    payload: WorkbenchParallelProcessingJobPayloadDto | Mapping[str, object],
    coordinator: ParallelWorkbenchProcessingCoordinatorPort,
) -> object:
    dto = (
        payload
        if isinstance(payload, WorkbenchParallelProcessingJobPayloadDto)
        else WorkbenchParallelProcessingJobPayloadDto.from_mapping(payload)
    )
    result = await coordinator.run_parallel_processing(dto.to_command())
    _ensure_parallel_processing_terminal_result(result)
    return result


@dataclass(frozen=True, slots=True)
class DefaultClaimObservationsRunner:
    """Production Prompt A runner for leased section work items.

    This runner performs only local section extraction and persistence.
    It does not run Prompt C and does not update the canonical registry.
    """

    repository: ClaimObservationsRunnerRepositoryPort
    generator: FaqWorkbenchClaimObservationsGeneratorPort
    persistence_service: FaqWorkbenchClaimObservationsService

    async def process_leased_claim_observations(
        self,
        command: ProcessLeasedClaimObservationsCommand,
    ) -> ProcessLeasedClaimObservationsResult:
        registry = await self.repository.get_fact_registry_for_run(
            project_id=command.queue_item.project_id,
            document_id=command.queue_item.document_id,
            processing_run_id=command.queue_item.processing_run_id,
        )
        if registry is None:
            raise DomainInvariantError(
                "claim observations runner requires fact registry"
            )

        latest_registry_snapshot = await self.repository.get_latest_registry_snapshot(
            project_id=command.queue_item.project_id,
            document_id=command.queue_item.document_id,
            processing_run_id=command.queue_item.processing_run_id,
        )
        if latest_registry_snapshot is None:
            raise DomainInvariantError(
                "claim observations runner requires latest registry snapshot"
            )
        registry_snapshot_payload = latest_registry_snapshot.entries_payload

        generation_result = None
        worker_id = command.queue_item.claimed_by_worker_id
        try:
            with workbench_qwen_worker_context(worker_id):
                generation_result = await self.generator.generate_findings(
                    section=command.section,
                    registry_snapshot=registry_snapshot_payload,
                )
        except Exception as exc:
            invocation = _llm_json_invocation_from_exception(exc)
            if invocation is not None:
                await self.persistence_service.persist_claim_observations_generation_error(
                    ProcessClaimObservationsGenerationErrorCommand(
                        section=command.section,
                        registry=registry,
                        registry_snapshot_payload=(registry_snapshot_payload),
                        invocation=invocation,
                    )
                )
            raise

        successful_attempt = next(
            (
                attempt
                for attempt in generation_result.invocation.attempts
                if attempt.status.value == "success"
            ),
            generation_result.invocation.attempts[-1],
        )

        persisted = await self.persistence_service.persist_claim_observations(
            ProcessClaimObservationsCommand(
                section=command.section,
                registry=registry,
                registry_snapshot_payload=registry_snapshot_payload,
                claim_observations=tuple(generation_result.claim_observations),
                model_name=successful_attempt.model,
                prompt_version="faq_claim_observations.v1",
                model_provider=successful_attempt.provider_id,
                api_key_slot=successful_attempt.api_key_slot,
                prompt_tokens=generation_result.invocation.token_usage.prompt_tokens,
                completion_tokens=(
                    generation_result.invocation.token_usage.completion_tokens
                ),
                total_tokens=generation_result.invocation.token_usage.total_tokens,
                raw_llm_output=generation_result.invocation.raw_text,
                raw_payload=generation_result.raw_payload,
                invocation_status=generation_result.invocation.status.value,
                route_attempts=tuple(
                    {
                        "provider_id": attempt.provider_id,
                        "model": attempt.model,
                        "api_key_slot": attempt.api_key_slot,
                        "attempt_index": attempt.attempt_index,
                        "status": attempt.status.value,
                        "error_kind": attempt.error_kind,
                        "cooldown_seconds": attempt.cooldown_seconds,
                    }
                    for attempt in generation_result.invocation.attempts
                ),
                llm_warnings=tuple(generation_result.warnings),
                llm_metrics=dict(generation_result.metrics),
            )
        )

        return ProcessLeasedClaimObservationsResult(
            claim_observations_node_run_id=persisted.node_run.node_run_id,
            claim_input_refs=persisted.claim_observation_ids,
        )


def _llm_json_invocation_from_exception(
    exc: BaseException,
) -> LlmJsonInvocationResult | None:
    for arg in getattr(exc, "args", ()):
        if isinstance(arg, LlmJsonInvocationResult):
            return arg
    return None


def make_workbench_claim_observations_generator(
    *,
    llm_json_invocation: LlmJsonInvocationPort | None = None,
    prompt_path: Path = Path("src/agent/prompts/faq_surface_claim_observations.ru.txt"),
) -> FaqWorkbenchClaimObservationsGenerator:
    return FaqWorkbenchClaimObservationsGenerator(
        llm_invocation=(
            llm_json_invocation
            if llm_json_invocation is not None
            else WorkbenchPromptAFallbackLlmJsonInvocationAdapter.create_default()
        ),
        config=FaqWorkbenchClaimObservationsGeneratorConfig(prompt_path=prompt_path),
    )


def make_workbench_claim_observations_runner(
    *,
    repository: ClaimObservationsRunnerRepositoryPort,
    id_factory: IdFactory,
    time_provider: TimeProvider | None = None,
    llm_json_invocation: LlmJsonInvocationPort | None = None,
    prompt_path: Path = Path("src/agent/prompts/faq_surface_claim_observations.ru.txt"),
) -> DefaultClaimObservationsRunner:
    return DefaultClaimObservationsRunner(
        repository=repository,
        generator=make_workbench_claim_observations_generator(
            llm_json_invocation=llm_json_invocation,
            prompt_path=prompt_path,
        ),
        persistence_service=FaqWorkbenchClaimObservationsService(
            repository=repository,
            id_factory=id_factory,
            time_provider=time_provider,
        ),
    )


def make_workbench_parallel_processing_dependencies(
    *,
    repository: ClaimObservationsRunnerRepositoryPort,
    id_factory: IdFactory | None = None,
    time_provider: TimeProvider | None = None,
    claim_observations_runner: object | None = None,
    llm_json_invocation: LlmJsonInvocationPort | None = None,
    registry_application_service: object | None = None,
    claim_observations_prompt_path: Path = Path(
        "src/agent/prompts/faq_surface_claim_observations.ru.txt"
    ),
) -> FaqWorkbenchParallelProcessingDependencies:
    """Build runtime dependencies for active parallel Workbench processing.

    The queue handler owns infrastructure defaults; composition owns object graph assembly.
    """

    id_factory = id_factory or UuidWorkbenchIdFactory()
    time_provider = time_provider or SystemWorkbenchTimeProvider()

    if claim_observations_runner is None:
        claim_observations_runner = make_workbench_claim_observations_runner(
            repository=repository,
            id_factory=id_factory,
            time_provider=time_provider,
            llm_json_invocation=llm_json_invocation,
            prompt_path=claim_observations_prompt_path,
        )

    dependencies = FaqWorkbenchParallelProcessingDependencies(
        id_factory=id_factory,
        claim_observations_runner=claim_observations_runner,
        canonicalization_barrier_service=None,
        drain_counts_provider=repository,
        lifecycle_completion_port=repository,
        registry_application_service=registry_application_service,
        llm_json_invocation=llm_json_invocation,
        time_provider=time_provider,
    )
    barrier_service = make_workbench_canonicalization_barrier_service_from_repository(
        repository=repository,
        dependencies=dependencies,
    )

    return FaqWorkbenchParallelProcessingDependencies(
        id_factory=id_factory,
        claim_observations_runner=claim_observations_runner,
        canonicalization_barrier_service=barrier_service,
        drain_counts_provider=repository,
        lifecycle_completion_port=repository,
        registry_application_service=registry_application_service,
        llm_json_invocation=llm_json_invocation,
        registry_merge_prompt_path=dependencies.registry_merge_prompt_path,
        time_provider=time_provider,
    )


def make_workbench_parallel_processing_coordinator(
    connection: object,
    *,
    claim_observations_runner: object | None = None,
    llm_json_invocation: LlmJsonInvocationPort | None = None,
    registry_application_service: object | None = None,
    id_factory: IdFactory | None = None,
    time_provider: TimeProvider | None = None,
    claim_observations_prompt_path: Path = Path(
        "src/agent/prompts/faq_surface_claim_observations.ru.txt"
    ),
) -> FaqWorkbenchParallelProcessingCoordinatorService:
    repository = _workbench_repository(connection)
    dependencies = make_workbench_parallel_processing_dependencies(
        repository=repository,
        id_factory=id_factory,
        time_provider=time_provider,
        claim_observations_runner=claim_observations_runner,
        llm_json_invocation=llm_json_invocation,
        registry_application_service=registry_application_service,
        claim_observations_prompt_path=claim_observations_prompt_path,
    )
    return make_workbench_parallel_processing_coordinator_from_repository(
        repository=repository,
        dependencies=dependencies,
    )


async def handle_workbench_parallel_processing_job_from_connection(
    *,
    payload: WorkbenchParallelProcessingJobPayloadDto | Mapping[str, object],
    connection: object,
    claim_observations_runner: object | None = None,
    llm_json_invocation: LlmJsonInvocationPort | None = None,
    registry_application_service: object | None = None,
    claim_observations_prompt_path: Path = Path(
        "src/agent/prompts/faq_surface_claim_observations.ru.txt"
    ),
) -> object:
    return await handle_workbench_parallel_processing_job(
        payload=payload,
        coordinator=make_workbench_parallel_processing_coordinator(
            connection,
            claim_observations_runner=claim_observations_runner,
            llm_json_invocation=llm_json_invocation,
            registry_application_service=registry_application_service,
            claim_observations_prompt_path=claim_observations_prompt_path,
        ),
    )


def _ensure_parallel_processing_terminal_result(result: object) -> None:
    completed_without_work_left = bool(
        getattr(result, "completed_without_work_left", False)
    )
    cycles = tuple(getattr(result, "cycles", ()) or ())

    if not completed_without_work_left:
        raise TransientJobError(
            "parallel Workbench processing reached max_cycles before terminal completion"
        )

    if not cycles:
        return

    last_cycle = cycles[-1]
    outcomes = tuple(
        str(outcome)
        for outcome in (
            tuple(getattr(last_cycle, "section_worker_outcomes", ()) or ())
            + tuple(getattr(last_cycle, "canonicalization_barrier_outcomes", ()) or ())
            + tuple(getattr(last_cycle, "registry_writer_outcomes", ()) or ())
        )
    )

    if "failed" in outcomes:
        raise PermanentJobError(
            "parallel Workbench processing reached failed terminal state"
        )

    transient_blockers = {
        "blocked_by_sections",
        "blocked_by_leases",
        "waiting_for_fresh_registry",
        "wait_for_snapshot",
        "keep_draining",
    }
    blocker = next(
        (outcome for outcome in outcomes if outcome in transient_blockers), None
    )
    if blocker is not None:
        raise TransientJobError(
            f"parallel Workbench processing is not terminal: {blocker}"
        )


def _required_text(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if value is None:
        raise DomainInvariantError(f"parallel queue payload requires {key}")
    text = str(value).strip()
    if not text:
        raise DomainInvariantError(f"parallel queue payload requires {key}")
    return text


def _optional_text(
    payload: Mapping[str, object],
    key: str,
    *,
    default: str,
) -> str:
    value = payload.get(key, default)
    text = str(value).strip()
    return text or default


def _positive_int(
    payload: Mapping[str, object],
    key: str,
    *,
    default: int,
) -> int:
    raw_value = payload.get(key, default)
    try:
        value = int(str(raw_value))
    except (TypeError, ValueError) as exc:
        raise DomainInvariantError(
            f"parallel queue payload {key} must be positive integer"
        ) from exc

    if value < 1:
        raise DomainInvariantError(
            f"parallel queue payload {key} must be positive integer"
        )
    return value


__all__ = [
    "DefaultClaimObservationsRunner",
    "PARALLEL_WORKBENCH_PROCESSING_TASK_TYPE",
    "ParallelWorkbenchProcessingCoordinatorPort",
    "UuidWorkbenchIdFactory",
    "WorkbenchParallelProcessingJobPayloadDto",
    "handle_workbench_parallel_processing_job",
    "handle_workbench_parallel_processing_job_from_connection",
    "_ensure_parallel_processing_terminal_result",
    "make_workbench_claim_observations_generator",
    "make_workbench_claim_observations_runner",
    "make_workbench_parallel_processing_coordinator",
    "make_workbench_parallel_processing_dependencies",
]
