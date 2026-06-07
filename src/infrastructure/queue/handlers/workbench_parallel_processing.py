from __future__ import annotations

import re

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timezone
from typing import Protocol, cast
from uuid import uuid4

from src.application.ports.faq_workbench_claim_observations_generator import (
    FaqWorkbenchClaimObservationsGenerationError,
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
    JsonValue,
    RegistrySnapshot,
)
from src.domain.project_plane.knowledge_workbench.documents import (
    DocumentSection,
    DocumentSectionStatus,
)
from src.domain.project_plane.knowledge_workbench.section_batch_queue import (
    SectionBatchQueueItem,
    SectionBatchQueueItemStatus,
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

_PROMPT_A_OVERSIZED_SPLIT_ERROR_KIND = "prompt_a_fallback_exhausted_request_too_large"
_OVERSIZED_SECTION_SPLIT_TARGET_CHARS = 6_000


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

    async def upsert_document_sections(
        self,
        sections: tuple[DocumentSection, ...],
    ) -> None: ...

    async def update_section_batch_queue_item(
        self,
        item: SectionBatchQueueItem,
    ) -> None: ...


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
            if invocation is not None and _prompt_a_invocation_requires_oversized_split(
                invocation
            ):
                return await self._split_oversized_section_and_persist_parent(
                    command=command,
                    registry=registry,
                    registry_snapshot_payload=registry_snapshot_payload,
                    invocation=invocation,
                )
            if isinstance(exc, FaqWorkbenchClaimObservationsGenerationError):
                raise
            if (
                invocation is not None
                and not _is_retryable_prompt_a_transient_generation_error(exc)
            ):
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

    async def _split_oversized_section_and_persist_parent(
        self,
        *,
        command: ProcessLeasedClaimObservationsCommand,
        registry: FactRegistry,
        registry_snapshot_payload: JsonValue,
        invocation: LlmJsonInvocationResult,
    ) -> ProcessLeasedClaimObservationsResult:
        section = command.section
        queue_item = command.queue_item
        child_texts = _split_oversized_section_text(section.raw_text)
        child_sections = _oversized_child_sections(
            section=section,
            child_texts=child_texts,
        )
        child_queue_items = _oversized_child_queue_items(
            parent_item=queue_item,
            child_sections=child_sections,
        )

        await self.repository.upsert_document_sections(child_sections)
        for child_queue_item in child_queue_items:
            await self.repository.update_section_batch_queue_item(child_queue_item)

        selected_attempt = invocation.attempts[-1]
        raw_payload: JsonValue = {
            "claim_observations": [],
            "oversized_section_split": {
                "reason": _PROMPT_A_OVERSIZED_SPLIT_ERROR_KIND,
                "parent_section_id": section.section_id,
                "parent_section_key": section.section_key,
                "child_section_ids": [
                    child_section.section_id for child_section in child_sections
                ],
                "child_queue_item_ids": [
                    child_queue_item.queue_item_id
                    for child_queue_item in child_queue_items
                ],
            },
        }

        persisted = await self.persistence_service.persist_claim_observations(
            ProcessClaimObservationsCommand(
                section=section,
                registry=registry,
                registry_snapshot_payload=registry_snapshot_payload,
                claim_observations=(),
                model_name=selected_attempt.model,
                prompt_version="faq_claim_observations.v1.oversized_split",
                model_provider=selected_attempt.provider_id,
                api_key_slot=selected_attempt.api_key_slot,
                prompt_tokens=invocation.token_usage.prompt_tokens,
                completion_tokens=invocation.token_usage.completion_tokens,
                total_tokens=invocation.token_usage.total_tokens,
                raw_llm_output=invocation.raw_text,
                raw_payload=raw_payload,
                invocation_status=invocation.status.value,
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
                    for attempt in invocation.attempts
                ),
                llm_warnings=("oversized_section_split",),
                llm_metrics={
                    "split_child_count": len(child_sections),
                    "split_reason": _PROMPT_A_OVERSIZED_SPLIT_ERROR_KIND,
                },
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
    result = getattr(exc, "result", None)
    if isinstance(result, LlmJsonInvocationResult):
        return result
    return None


def _is_retryable_prompt_a_transient_generation_error(exc: BaseException) -> bool:
    return isinstance(exc, FaqWorkbenchClaimObservationsGenerationError)


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


def _prompt_a_invocation_requires_oversized_split(
    invocation: LlmJsonInvocationResult,
) -> bool:
    failure = invocation.failure
    return (
        failure is not None
        and failure.error_kind == _PROMPT_A_OVERSIZED_SPLIT_ERROR_KIND
    )


def _oversized_child_sections(
    *,
    section: DocumentSection,
    child_texts: tuple[str, ...],
) -> tuple[DocumentSection, ...]:
    part_count = len(child_texts)
    if part_count < 2:
        raise DomainInvariantError(
            "oversized section split requires at least two child sections"
        )

    child_sections: list[DocumentSection] = []
    for index, child_text in enumerate(child_texts, start=1):
        metadata = dict(section.metadata)
        metadata.update(
            {
                "split_reason": _PROMPT_A_OVERSIZED_SPLIT_ERROR_KIND,
                "split_parent_section_id": section.section_id,
                "split_parent_section_key": section.section_key,
                "split_part_index": index,
                "split_part_count": part_count,
            }
        )
        child_sections.append(
            DocumentSection(
                section_id=f"{section.section_id}-split-{index}",
                document_id=section.document_id,
                project_id=section.project_id,
                section_index=section.section_index,
                section_key=f"{section.section_key}.split.{index}",
                heading_path=section.heading_path,
                title=f"{section.title} · часть {index}/{part_count}",
                raw_text=child_text,
                normalized_text=child_text,
                source_refs=section.source_refs,
                source_chunk_indexes=section.source_chunk_indexes,
                status=DocumentSectionStatus.PENDING,
                parent_section_id=section.section_id,
                metadata=metadata,
            )
        )

    return tuple(child_sections)


def _oversized_child_queue_items(
    *,
    parent_item: SectionBatchQueueItem,
    child_sections: tuple[DocumentSection, ...],
) -> tuple[SectionBatchQueueItem, ...]:
    child_items: list[SectionBatchQueueItem] = []
    for index, child_section in enumerate(child_sections, start=1):
        child_items.append(
            SectionBatchQueueItem(
                queue_item_id=f"{parent_item.queue_item_id}-split-{index}",
                batch_plan_id=parent_item.batch_plan_id,
                processing_run_id=parent_item.processing_run_id,
                project_id=parent_item.project_id,
                document_id=parent_item.document_id,
                section_id=child_section.section_id,
                section_key=child_section.section_key,
                section_index=child_section.section_index,
                lane_id=parent_item.lane_id,
                lane_index=parent_item.lane_index + index,
                observed_registry_snapshot_id=(
                    parent_item.observed_registry_snapshot_id
                ),
                observed_registry_snapshot_sequence=(
                    parent_item.observed_registry_snapshot_sequence
                ),
                status=SectionBatchQueueItemStatus.READY,
                claimed_by_worker_id=None,
                lease_expires_at=None,
                claim_observations_node_run_id=None,
                registry_application_queue_item_id=None,
                error_kind=None,
                attempt_count=0,
                created_at=parent_item.created_at,
                updated_at=parent_item.updated_at,
            )
        )
    return tuple(child_items)


def _split_oversized_section_text(
    text: str,
    *,
    target_chars: int = _OVERSIZED_SECTION_SPLIT_TARGET_CHARS,
) -> tuple[str, ...]:
    if target_chars < 1_000:
        raise DomainInvariantError("oversized section split target is too small")
    if not text.strip():
        raise DomainInvariantError("oversized section split requires non-empty text")

    blocks = _text_blocks_preserving_separators(text)
    chunks: list[str] = []
    current = ""

    for block in blocks:
        if len(block) > target_chars:
            if current.strip():
                chunks.append(current)
                current = ""
            chunks.extend(_split_large_text_block(block, target_chars=target_chars))
            continue

        if current and len(current) + len(block) > target_chars:
            chunks.append(current)
            current = block
            continue

        current += block

    if current.strip():
        chunks.append(current)

    chunks = [chunk for chunk in chunks if chunk.strip()]
    if len(chunks) >= 2:
        return tuple(chunks)

    return tuple(_split_large_text_block(text, target_chars=target_chars))


def _text_blocks_preserving_separators(text: str) -> tuple[str, ...]:
    parts = re.split(r"(\n{2,})", text)
    blocks: list[str] = []
    index = 0
    while index < len(parts):
        content = parts[index]
        separator = parts[index + 1] if index + 1 < len(parts) else ""
        block = content + separator
        if block:
            blocks.append(block)
        index += 2
    return tuple(blocks)


def _split_large_text_block(
    text: str,
    *,
    target_chars: int,
) -> tuple[str, ...]:
    chunks: list[str] = []
    remaining = text

    while len(remaining) > target_chars:
        cut_index = _best_semantic_cut_index(remaining, target_chars=target_chars)
        chunks.append(remaining[:cut_index])
        remaining = remaining[cut_index:]

    if remaining.strip():
        chunks.append(remaining)

    chunks = [chunk for chunk in chunks if chunk.strip()]
    if len(chunks) < 2:
        raise DomainInvariantError(
            "oversized section split could not find a safe boundary"
        )
    return tuple(chunks)


def _best_semantic_cut_index(text: str, *, target_chars: int) -> int:
    lower_bound = max(1, target_chars // 2)
    upper_bound = min(len(text) - 1, target_chars)

    candidates: list[int] = []
    for marker in ("\n## ", "\n### ", "\n\n", "\n", ". ", "! ", "? ", "; "):
        index = text.rfind(marker, lower_bound, upper_bound)
        if index > 0:
            candidates.append(index + len(marker))

    if candidates:
        return max(candidates)

    return upper_bound


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
