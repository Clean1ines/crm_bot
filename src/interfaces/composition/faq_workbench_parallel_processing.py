from __future__ import annotations

import inspect
from pathlib import Path
from dataclasses import dataclass
from typing import Callable, Protocol, TypeVar, cast

import asyncpg

from src.application.services.faq_workbench_canonicalization_barrier_service import (
    FaqWorkbenchCanonicalizationBarrierService,
)
from src.application.services.faq_workbench_local_claim_graph_loader_service import (
    FaqWorkbenchLocalClaimGraphLoaderService,
)
from src.application.services.faq_workbench_local_claim_retrieval_service import (
    FaqWorkbenchLocalClaimRetrievalService,
    LocalClaimRetrievalSurfaceReaderPort,
)
from src.application.services.faq_workbench_local_claim_retrieval_surface_indexing_service import (
    FaqWorkbenchLocalClaimRetrievalSurfaceIndexingService,
    LocalClaimRetrievalSurfaceRepositoryPort,
)
from src.application.services.faq_workbench_registry_application_service import (
    FaqWorkbenchRegistryApplicationService,
)
from src.application.services.faq_workbench_registry_merge_service import (
    FaqWorkbenchRegistryMergeService,
)
from src.application.services.faq_workbench_registry_materialization_service import (
    FaqWorkbenchRegistryMaterializationService,
)
from src.infrastructure.llm.faq_workbench_registry_merge_generator import (
    FaqWorkbenchRegistryMergeGenerator,
    FaqWorkbenchRegistryMergeGeneratorConfig,
)
from src.infrastructure.llm.groq_llm_json_invocation import (
    GroqLlmJsonInvocationAdapter,
)
from src.infrastructure.llm.workbench_local_claim_embedding_adapter import (
    WorkbenchLocalClaimEmbeddingAdapter,
)
from src.application.services.faq_workbench_parallel_processing_adapters import (
    FaqWorkbenchCanonicalizationBarrierProcessorAdapter,
    FaqWorkbenchParallelRegistryApplicationProcessorAdapter,
    FaqWorkbenchParallelSectionProcessorAdapter,
)
from src.application.services.faq_workbench_parallel_processing_coordinator_service import (
    FaqWorkbenchParallelProcessingCoordinatorService,
)
from src.application.services.faq_workbench_registry_application_work_item_processor_service import (
    FaqWorkbenchRegistryApplicationWorkItemProcessorService,
)
from src.application.services.faq_workbench_section_work_item_lease_service import (
    FaqWorkbenchSectionWorkItemLeaseService,
)
from src.application.services.faq_workbench_section_work_item_processor_service import (
    FaqWorkbenchSectionWorkItemProcessorService,
)
from src.domain.project_plane.knowledge_workbench import DomainInvariantError
from src.infrastructure.db.knowledge_workbench_repository import (
    KnowledgeWorkbenchRepository,
)


_T = TypeVar("_T")


def _workbench_repository(connection: object) -> KnowledgeWorkbenchRepository:
    repository_factory = cast(
        Callable[[object], KnowledgeWorkbenchRepository],
        KnowledgeWorkbenchRepository,
    )
    return repository_factory(connection)


class WorkbenchParallelProcessingDbPool(Protocol):
    async def acquire(self): ...


@dataclass(frozen=True, slots=True)
class FaqWorkbenchParallelProcessingDependencies:
    """Injected dependencies for the active parallel Workbench boundary.

    This composition layer must not resurrect the retired sequential compiler or
    the old per-section Prompt C merge path. Section workers receive only a
    claim-observations runner. Document-level canonicalization is provided as a
    separate barrier service and adapted into the coordinator.
    """

    id_factory: object
    queue: object | None = None
    claim_observations_runner: object | None = None
    canonicalization_barrier_service: object | None = None
    drain_counts_provider: object | None = None
    integrity_counts_provider: object | None = None
    lifecycle_completion_port: object | None = None
    registry_application_service: object | None = None
    llm_json_invocation: object | None = None
    registry_merge_prompt_path: Path = Path(
        "src/agent/prompts/faq_surface_registry_merge.ru.txt"
    )
    time_provider: object | None = None


async def make_workbench_parallel_processing_coordinator(
    *,
    pool: WorkbenchParallelProcessingDbPool,
    dependencies: FaqWorkbenchParallelProcessingDependencies,
) -> FaqWorkbenchParallelProcessingCoordinatorService:
    async with cast(asyncpg.Pool, pool).acquire() as connection:
        repository = _workbench_repository(connection)
        return make_workbench_parallel_processing_coordinator_from_repository(
            repository=repository,
            dependencies=dependencies,
        )


def make_workbench_parallel_processing_coordinator_from_repository(
    *,
    repository: object,
    dependencies: FaqWorkbenchParallelProcessingDependencies,
) -> FaqWorkbenchParallelProcessingCoordinatorService:
    section_processor = make_workbench_section_processor_from_repository(
        repository=repository,
        dependencies=dependencies,
    )
    registry_processor = make_workbench_registry_application_processor_from_repository(
        repository=repository,
        dependencies=dependencies,
    )

    canonicalization_processor = None
    if dependencies.canonicalization_barrier_service is not None:
        canonicalization_processor = _instantiate_with_available_kwargs(
            FaqWorkbenchCanonicalizationBarrierProcessorAdapter,
            barrier_service=dependencies.canonicalization_barrier_service,
        )

    return _instantiate_with_available_kwargs(
        FaqWorkbenchParallelProcessingCoordinatorService,
        section_processor=FaqWorkbenchParallelSectionProcessorAdapter(
            lease_service=_instantiate_with_available_kwargs(
                FaqWorkbenchSectionWorkItemLeaseService,
                repository=repository,
                id_factory=dependencies.id_factory,
                time_provider=dependencies.time_provider,
            ),
            processor=section_processor,
        ),
        registry_processor=FaqWorkbenchParallelRegistryApplicationProcessorAdapter(
            processor=registry_processor,
        ),
        canonicalization_barrier_processor=canonicalization_processor,
        drain_counts_provider=(
            dependencies.drain_counts_provider
            if dependencies.drain_counts_provider is not None
            else repository
        ),
        integrity_counts_provider=(
            dependencies.integrity_counts_provider
            if dependencies.integrity_counts_provider is not None
            else repository
        ),
        lifecycle_completion_port=(
            dependencies.lifecycle_completion_port
            if dependencies.lifecycle_completion_port is not None
            else repository
        ),
    )


async def make_workbench_section_work_item_processor(
    *,
    pool: WorkbenchParallelProcessingDbPool,
    dependencies: FaqWorkbenchParallelProcessingDependencies,
) -> FaqWorkbenchSectionWorkItemProcessorService:
    async with cast(asyncpg.Pool, pool).acquire() as connection:
        repository = _workbench_repository(connection)
        return make_workbench_section_processor_from_repository(
            repository=repository,
            dependencies=dependencies,
        )


def make_workbench_section_processor_from_repository(
    *,
    repository: object,
    dependencies: FaqWorkbenchParallelProcessingDependencies,
) -> FaqWorkbenchSectionWorkItemProcessorService:
    if dependencies.claim_observations_runner is None:
        raise DomainInvariantError(
            "parallel Workbench composition requires claim_observations_runner"
        )

    graph_loader = _instantiate_with_available_kwargs(
        FaqWorkbenchLocalClaimGraphLoaderService,
        repository=repository,
    )
    local_claim_retrieval_surface_indexing_service = (
        FaqWorkbenchLocalClaimRetrievalSurfaceIndexingService(
            graph_loader=graph_loader,
            repository=cast(LocalClaimRetrievalSurfaceRepositoryPort, repository),
            embedding_service=WorkbenchLocalClaimEmbeddingAdapter(),
        )
    )

    return _instantiate_with_available_kwargs(
        FaqWorkbenchSectionWorkItemProcessorService,
        repository=repository,
        claim_observations_runner=dependencies.claim_observations_runner,
        id_factory=dependencies.id_factory,
        time_provider=dependencies.time_provider,
        local_claim_retrieval_surface_indexing_service=(
            local_claim_retrieval_surface_indexing_service
        ),
    )


def make_workbench_canonicalization_barrier_service_from_repository(
    *,
    repository: object,
    dependencies: FaqWorkbenchParallelProcessingDependencies,
) -> FaqWorkbenchCanonicalizationBarrierService:
    """Build the real document-level canonicalization barrier service.

    This is the production dependency graph for:
    local claim artifacts -> canonicalization units -> Prompt C -> fact registry snapshot.

    The section worker still receives only claim_observations_runner.
    """

    graph_loader = _instantiate_with_available_kwargs(
        FaqWorkbenchLocalClaimGraphLoaderService,
        repository=repository,
    )
    local_claim_retrieval_surface_indexing_service = (
        FaqWorkbenchLocalClaimRetrievalSurfaceIndexingService(
            graph_loader=graph_loader,
            repository=cast(LocalClaimRetrievalSurfaceRepositoryPort, repository),
            embedding_service=WorkbenchLocalClaimEmbeddingAdapter(),
        )
    )
    local_claim_retrieval_service = FaqWorkbenchLocalClaimRetrievalService(
        graph_loader=graph_loader,
        retrieval_surface_indexing_service=local_claim_retrieval_surface_indexing_service,
        retrieval_surface_reader=cast(LocalClaimRetrievalSurfaceReaderPort, repository),
    )
    llm_json_invocation = (
        dependencies.llm_json_invocation
        if dependencies.llm_json_invocation is not None
        else GroqLlmJsonInvocationAdapter.create_default()
    )
    registry_merge_generator = _instantiate_with_available_kwargs(
        FaqWorkbenchRegistryMergeGenerator,
        llm_invocation=llm_json_invocation,
        config=FaqWorkbenchRegistryMergeGeneratorConfig(
            prompt_path=dependencies.registry_merge_prompt_path,
        ),
        id_factory=dependencies.id_factory,
    )
    registry_merge_service = _instantiate_with_available_kwargs(
        FaqWorkbenchRegistryMergeService,
        repository=repository,
        id_factory=dependencies.id_factory,
        time_provider=dependencies.time_provider,
    )
    registry_application_service = (
        dependencies.registry_application_service
        if dependencies.registry_application_service is not None
        else _instantiate_with_available_kwargs(
            FaqWorkbenchRegistryApplicationService,
            repository=repository,
            id_factory=dependencies.id_factory,
            time_provider=dependencies.time_provider,
        )
    )
    registry_materialization_service = _instantiate_with_available_kwargs(
        FaqWorkbenchRegistryMaterializationService,
        repository=repository,
    )

    return _instantiate_with_available_kwargs(
        FaqWorkbenchCanonicalizationBarrierService,
        repository=repository,
        local_claim_retrieval_service=local_claim_retrieval_service,
        registry_merge_generator=registry_merge_generator,
        registry_merge_service=registry_merge_service,
        registry_application_service=registry_application_service,
        registry_materialization_service=registry_materialization_service,
        id_factory=dependencies.id_factory,
    )


def make_workbench_registry_application_processor_from_repository(
    *,
    repository: object,
    dependencies: FaqWorkbenchParallelProcessingDependencies,
) -> FaqWorkbenchRegistryApplicationWorkItemProcessorService:
    return _instantiate_with_available_kwargs(
        FaqWorkbenchRegistryApplicationWorkItemProcessorService,
        repository=repository,
        id_factory=dependencies.id_factory,
        time_provider=dependencies.time_provider,
        registry_application_service=dependencies.registry_application_service,
    )


def _instantiate_with_available_kwargs(
    cls: Callable[..., _T],
    **available: object,
) -> _T:
    signature = inspect.signature(cls)
    kwargs: dict[str, object] = {}

    for name, parameter in signature.parameters.items():
        if name == "self":
            continue
        if name in available and available[name] is not None:
            kwargs[name] = available[name]
            continue
        if parameter.default is not inspect.Parameter.empty:
            continue
        raise DomainInvariantError(
            f"cannot build {getattr(cls, '__name__', cls)!s}: missing dependency {name}"
        )

    return cls(**kwargs)


__all__ = [
    "FaqWorkbenchParallelProcessingDependencies",
    "make_workbench_canonicalization_barrier_service_from_repository",
    "make_workbench_parallel_processing_coordinator",
    "make_workbench_parallel_processing_coordinator_from_repository",
    "make_workbench_registry_application_processor_from_repository",
    "make_workbench_section_processor_from_repository",
    "make_workbench_section_work_item_processor",
]
