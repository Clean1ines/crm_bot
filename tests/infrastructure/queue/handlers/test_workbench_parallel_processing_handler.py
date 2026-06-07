from __future__ import annotations

import importlib.abc
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from src.application.services.faq_workbench_parallel_processing_coordinator_service import (
    RunParallelWorkbenchProcessingCommand,
)
from src.domain.project_plane.knowledge_workbench import DomainInvariantError
from src.infrastructure.queue.handlers import workbench_parallel_processing as handler
from src.infrastructure.queue.job_exceptions import (
    PermanentJobError,
    TransientJobError,
)
from src.infrastructure.queue.handlers.workbench_parallel_processing import (
    PARALLEL_WORKBENCH_PROCESSING_TASK_TYPE,
    WorkbenchParallelProcessingJobPayloadDto,
    handle_workbench_parallel_processing_job,
)


@dataclass(frozen=True, slots=True)
class FakeRunResult:
    completed_without_work_left: bool = True


@dataclass(slots=True)
class FakeCoordinator:
    commands: list[RunParallelWorkbenchProcessingCommand] = field(default_factory=list)

    async def run_parallel_processing(
        self,
        command: RunParallelWorkbenchProcessingCommand,
    ) -> FakeRunResult:
        self.commands.append(command)
        return FakeRunResult()


class FakeClaimObservationsRunner:
    pass


class FakeLlmJsonInvocation:
    pass


class FakeRegistryApplicationService:
    pass


class FakeIdFactory:
    def new_id(self, prefix: str) -> str:
        return f"{prefix}-1"


class FakeRepository:
    pass


def test_parallel_queue_payload_defaults_to_four_section_workers() -> None:
    payload = WorkbenchParallelProcessingJobPayloadDto(
        project_id="project-1",
        document_id="document-1",
        processing_run_id="processing-run-1",
    )

    command = payload.to_command()

    assert command.project_id == "project-1"
    assert command.document_id == "document-1"
    assert command.processing_run_id == "processing-run-1"
    assert command.section_worker_count == 4
    assert command.worker_id_prefix == "workbench-parallel"
    assert command.lease_seconds == 300
    assert command.max_cycles == 10_000
    assert command.max_registry_drain_steps_per_cycle == 10_000


def test_parallel_queue_payload_from_mapping_coerces_positive_ints() -> None:
    payload = WorkbenchParallelProcessingJobPayloadDto.from_mapping(
        {
            "project_id": "project-1",
            "document_id": "document-1",
            "processing_run_id": "processing-run-1",
            "section_worker_count": "4",
            "worker_id_prefix": "parallel-test",
            "lease_seconds": "120",
            "max_cycles": "7",
            "max_registry_drain_steps_per_cycle": "9",
        }
    )

    assert payload.section_worker_count == 4
    assert payload.worker_id_prefix == "parallel-test"
    assert payload.lease_seconds == 120
    assert payload.max_cycles == 7
    assert payload.max_registry_drain_steps_per_cycle == 9


@pytest.mark.asyncio
async def test_parallel_handler_invokes_coordinator_with_command_from_dto() -> None:
    coordinator = FakeCoordinator()
    payload = WorkbenchParallelProcessingJobPayloadDto(
        project_id="project-1",
        document_id="document-1",
        processing_run_id="processing-run-1",
        section_worker_count=4,
        worker_id_prefix="test-worker",
        lease_seconds=77,
        max_cycles=11,
        max_registry_drain_steps_per_cycle=13,
    )

    result = await handle_workbench_parallel_processing_job(
        payload=payload,
        coordinator=coordinator,
    )

    assert result.completed_without_work_left is True
    assert len(coordinator.commands) == 1
    command = coordinator.commands[0]
    assert command.project_id == "project-1"
    assert command.document_id == "document-1"
    assert command.processing_run_id == "processing-run-1"
    assert command.section_worker_count == 4
    assert command.worker_id_prefix == "test-worker"
    assert command.lease_seconds == 77
    assert command.max_cycles == 11
    assert command.max_registry_drain_steps_per_cycle == 13


@pytest.mark.asyncio
async def test_parallel_handler_accepts_raw_mapping_payload() -> None:
    coordinator = FakeCoordinator()

    await handle_workbench_parallel_processing_job(
        payload={
            "project_id": "project-1",
            "document_id": "document-1",
            "processing_run_id": "processing-run-1",
        },
        coordinator=coordinator,
    )

    assert len(coordinator.commands) == 1
    assert coordinator.commands[0].section_worker_count == 4


def test_parallel_payload_rejects_missing_required_ids() -> None:
    with pytest.raises(DomainInvariantError, match="project_id"):
        WorkbenchParallelProcessingJobPayloadDto.from_mapping(
            {
                "document_id": "document-1",
                "processing_run_id": "processing-run-1",
            }
        )


def test_parallel_payload_rejects_non_positive_worker_count() -> None:
    with pytest.raises(DomainInvariantError, match="section_worker_count"):
        WorkbenchParallelProcessingJobPayloadDto(
            project_id="project-1",
            document_id="document-1",
            processing_run_id="processing-run-1",
            section_worker_count=0,
        )


def test_parallel_task_type_is_explicit_but_not_registered_here() -> None:
    assert PARALLEL_WORKBENCH_PROCESSING_TASK_TYPE == (
        "process_workbench_parallel_processing"
    )


def test_parallel_queue_handler_factory_delegates_to_composition(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeKnowledgeWorkbenchRepository:
        def __init__(self, connection: object) -> None:
            captured["connection"] = connection

    def fake_make_barrier(*, repository: object, dependencies: object) -> object:
        captured["barrier_repository"] = repository
        captured["barrier_dependencies"] = dependencies
        return object()

    def fake_make_coordinator(*, repository: object, dependencies: object) -> object:
        captured["coordinator_repository"] = repository
        captured["coordinator_dependencies"] = dependencies
        return object()

    monkeypatch.setattr(
        handler, "KnowledgeWorkbenchRepository", FakeKnowledgeWorkbenchRepository
    )
    monkeypatch.setattr(
        handler,
        "make_workbench_canonicalization_barrier_service_from_repository",
        fake_make_barrier,
    )
    monkeypatch.setattr(
        handler,
        "make_workbench_parallel_processing_coordinator_from_repository",
        fake_make_coordinator,
    )

    connection = object()
    claim_runner = FakeClaimObservationsRunner()
    llm = FakeLlmJsonInvocation()
    registry_application_service = FakeRegistryApplicationService()
    id_factory = FakeIdFactory()

    coordinator = handler.make_workbench_parallel_processing_coordinator(
        connection,
        claim_observations_runner=claim_runner,
        llm_json_invocation=llm,
        registry_application_service=registry_application_service,
        id_factory=id_factory,
    )

    assert coordinator is captured["coordinator_repository"] or coordinator is not None
    assert captured["connection"] is connection
    assert captured["barrier_repository"] is captured["coordinator_repository"]

    barrier_dependencies = captured["barrier_dependencies"]
    coordinator_dependencies = captured["coordinator_dependencies"]

    assert barrier_dependencies.claim_observations_runner is claim_runner
    assert barrier_dependencies.llm_json_invocation is llm
    assert (
        barrier_dependencies.registry_application_service
        is registry_application_service
    )
    assert barrier_dependencies.canonicalization_barrier_service is None

    assert coordinator_dependencies.claim_observations_runner is claim_runner
    assert coordinator_dependencies.llm_json_invocation is llm
    assert (
        coordinator_dependencies.registry_application_service
        is registry_application_service
    )
    assert coordinator_dependencies.canonicalization_barrier_service is not None


def test_parallel_queue_handler_no_longer_hand_builds_coordinator_services() -> None:
    loader = handler.__loader__
    assert isinstance(loader, importlib.abc.InspectLoader)
    source = loader.get_source(handler.__name__)
    assert source is not None

    assert "make_workbench_parallel_processing_coordinator_from_repository" in source
    assert "make_workbench_canonicalization_barrier_service_from_repository" in source
    assert "FaqWorkbenchParallelProcessingDependencies" in source

    assert "FaqWorkbenchSectionWorkItemProcessorService" not in source
    assert "FaqWorkbenchRegistryApplicationWorkItemProcessorService" not in source
    assert "_instantiate_with_available_kwargs" not in source
    assert "inspect.signature" not in source


class FakeGenerator:
    pass


class FakePersistenceService:
    pass


def test_parallel_queue_handler_builds_default_claim_observations_generator_with_pinned_workbench_adapter_legacy_name(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeWorkbenchQwenLlmJsonInvocationAdapter:
        @classmethod
        def create_default(cls):
            captured["create_default_called"] = True
            return FakeLlmJsonInvocation()

    class FakeFaqWorkbenchClaimObservationsGenerator:
        def __init__(self, *, llm_invocation: object, config: object) -> None:
            captured["llm_invocation"] = llm_invocation
            captured["config"] = config

    class FakeFaqWorkbenchClaimObservationsGeneratorConfig:
        def __init__(self, *, prompt_path: Path) -> None:
            self.prompt_path = prompt_path

    monkeypatch.setattr(
        handler,
        "WorkbenchQwenLlmJsonInvocationAdapter",
        FakeWorkbenchQwenLlmJsonInvocationAdapter,
    )
    monkeypatch.setattr(
        handler,
        "FaqWorkbenchClaimObservationsGenerator",
        FakeFaqWorkbenchClaimObservationsGenerator,
    )
    monkeypatch.setattr(
        handler,
        "FaqWorkbenchClaimObservationsGeneratorConfig",
        FakeFaqWorkbenchClaimObservationsGeneratorConfig,
    )

    generator = handler.make_workbench_claim_observations_generator()

    assert generator is not None
    assert captured["create_default_called"] is True
    assert captured["llm_invocation"].__class__ is FakeLlmJsonInvocation
    assert captured["config"].prompt_path == Path(
        "src/agent/prompts/faq_surface_claim_observations.ru.txt"
    )


def test_parallel_queue_handler_builds_default_claim_observations_runner(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_make_generator(
        *, llm_json_invocation: object | None = None, prompt_path: Path
    ):
        captured["llm_json_invocation"] = llm_json_invocation
        captured["prompt_path"] = prompt_path
        return FakeGenerator()

    class FakeFaqWorkbenchClaimObservationsService:
        def __init__(
            self,
            *,
            repository: object,
            id_factory: object,
            time_provider: object | None = None,
        ) -> None:
            captured["repository"] = repository
            captured["id_factory"] = id_factory
            captured["time_provider"] = time_provider

    monkeypatch.setattr(
        handler,
        "make_workbench_claim_observations_generator",
        fake_make_generator,
    )
    monkeypatch.setattr(
        handler,
        "FaqWorkbenchClaimObservationsService",
        FakeFaqWorkbenchClaimObservationsService,
    )

    repository = FakeRepository()
    id_factory = FakeIdFactory()
    llm = FakeLlmJsonInvocation()

    runner = handler.make_workbench_claim_observations_runner(
        repository=repository,
        id_factory=id_factory,
        llm_json_invocation=llm,
        prompt_path=Path("custom_prompt.txt"),
    )

    assert runner.__class__.__name__ == "DefaultClaimObservationsRunner"
    assert runner.repository is repository
    assert runner.generator.__class__ is FakeGenerator
    assert (
        runner.persistence_service.__class__ is FakeFaqWorkbenchClaimObservationsService
    )
    assert captured["llm_json_invocation"] is llm
    assert captured["prompt_path"] == Path("custom_prompt.txt")
    assert captured["repository"] is repository
    assert captured["id_factory"] is id_factory


def test_parallel_queue_handler_dependencies_build_default_runner_when_not_injected(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_make_runner(**kwargs):
        captured["runner_kwargs"] = kwargs
        return FakeClaimObservationsRunner()

    def fake_make_barrier(*, repository: object, dependencies: object) -> object:
        captured["barrier_dependencies"] = dependencies
        return object()

    monkeypatch.setattr(
        handler, "make_workbench_claim_observations_runner", fake_make_runner
    )
    monkeypatch.setattr(
        handler,
        "make_workbench_canonicalization_barrier_service_from_repository",
        fake_make_barrier,
    )

    repository = FakeRepository()
    id_factory = FakeIdFactory()
    llm = FakeLlmJsonInvocation()

    dependencies = handler.make_workbench_parallel_processing_dependencies(
        repository=repository,
        id_factory=id_factory,
        claim_observations_runner=None,
        llm_json_invocation=llm,
        claim_observations_prompt_path=Path("prompt-a.txt"),
    )

    assert (
        dependencies.claim_observations_runner.__class__ is FakeClaimObservationsRunner
    )
    assert dependencies.canonicalization_barrier_service is not None
    assert captured["runner_kwargs"]["repository"] is repository
    assert captured["runner_kwargs"]["id_factory"] is id_factory
    assert captured["runner_kwargs"]["llm_json_invocation"] is llm
    assert captured["runner_kwargs"]["prompt_path"] == Path("prompt-a.txt")
    assert captured["barrier_dependencies"].claim_observations_runner.__class__ is (
        FakeClaimObservationsRunner
    )


def test_parallel_queue_handler_no_longer_requires_manual_claim_observations_runner() -> (
    None
):
    loader = handler.__loader__
    assert isinstance(loader, importlib.abc.InspectLoader)
    source = loader.get_source(handler.__name__)
    assert source is not None

    assert "make_workbench_claim_observations_runner" in source
    assert "make_workbench_claim_observations_generator" in source
    assert "WorkbenchQwenLlmJsonInvocationAdapter.create_default()" in source
    assert "GroqLlmJsonInvocationAdapter.create_default()" not in source
    assert "llama-3.1-8b-instant" not in source
    assert "faq_surface_claim_observations.ru.txt" in source
    assert (
        "parallel queue handler requires " + "claim_observations_runner" not in source
    )


@dataclass(frozen=True, slots=True)
class FakeParallelCycle:
    section_worker_outcomes: tuple[str, ...] = ("no_work",)
    canonicalization_barrier_outcomes: tuple[str, ...] = ("already_canonicalized",)
    registry_writer_outcomes: tuple[str, ...] = ("no_work",)


@dataclass(frozen=True, slots=True)
class FakeParallelResult:
    completed_without_work_left: bool
    cycles: tuple[FakeParallelCycle, ...]


def test_parallel_handler_terminal_guard_accepts_terminal_success() -> None:
    handler._ensure_parallel_processing_terminal_result(
        FakeParallelResult(
            completed_without_work_left=True,
            cycles=(FakeParallelCycle(),),
        )
    )


def test_parallel_handler_terminal_guard_retries_when_max_cycles_exhausted_with_work_left() -> (
    None
):
    with pytest.raises(TransientJobError, match="max_cycles"):
        handler._ensure_parallel_processing_terminal_result(
            FakeParallelResult(
                completed_without_work_left=False,
                cycles=(
                    FakeParallelCycle(
                        section_worker_outcomes=("claim_observations_persisted",),
                        canonicalization_barrier_outcomes=("blocked_by_sections",),
                        registry_writer_outcomes=("no_work",),
                    ),
                ),
            )
        )


@pytest.mark.parametrize(
    "outcome",
    [
        "blocked_by_sections",
        "blocked_by_leases",
        "waiting_for_fresh_registry",
        "wait_for_snapshot",
        "keep_draining",
    ],
)
def test_parallel_handler_terminal_guard_retries_transient_blocked_terminal_cycles(
    outcome: str,
) -> None:
    with pytest.raises(TransientJobError, match=outcome):
        handler._ensure_parallel_processing_terminal_result(
            FakeParallelResult(
                completed_without_work_left=True,
                cycles=(
                    FakeParallelCycle(
                        canonicalization_barrier_outcomes=(outcome,),
                    ),
                ),
            )
        )


def test_parallel_handler_terminal_guard_fails_failed_terminal_cycles_permanently() -> (
    None
):
    with pytest.raises(PermanentJobError, match="failed terminal"):
        handler._ensure_parallel_processing_terminal_result(
            FakeParallelResult(
                completed_without_work_left=True,
                cycles=(
                    FakeParallelCycle(
                        canonicalization_barrier_outcomes=("failed",),
                    ),
                ),
            )
        )


@pytest.mark.asyncio
async def test_parallel_handler_raises_retry_instead_of_returning_non_terminal_result() -> (
    None
):
    class NonTerminalCoordinator:
        async def run_parallel_processing(self, command):
            return FakeParallelResult(
                completed_without_work_left=False,
                cycles=(
                    FakeParallelCycle(
                        section_worker_outcomes=("claim_observations_persisted",),
                        canonicalization_barrier_outcomes=("blocked_by_sections",),
                    ),
                ),
            )

    with pytest.raises(TransientJobError, match="max_cycles"):
        await handler.handle_workbench_parallel_processing_job(
            payload={
                "project_id": "project-1",
                "document_id": "document-1",
                "processing_run_id": "run-1",
                "section_worker_count": 1,
                "max_cycles": 1,
            },
            coordinator=NonTerminalCoordinator(),
        )
