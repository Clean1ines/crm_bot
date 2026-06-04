from __future__ import annotations

import importlib.abc
from dataclasses import dataclass
from pathlib import Path

import pytest

from src.domain.project_plane.knowledge_workbench import DomainInvariantError
from src.interfaces.composition import faq_workbench_parallel_processing as composition


class FakeIdFactory:
    def new_id(self, prefix: str) -> str:
        return f"{prefix}-1"


class FakeRepository:
    pass


class FakeClaimObservationsRunner:
    pass


class FakeCanonicalizationBarrierService:
    pass


class FakeRegistryApplicationService:
    pass


class FakeLlmJsonInvocation:
    async def invoke_json(self, request):
        raise AssertionError("not called by composition factory tests")


@dataclass(slots=True)
class FakePoolConnectionManager:
    connection: object

    async def __aenter__(self) -> object:
        return self.connection

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


@dataclass(slots=True)
class FakePool:
    connection: object
    acquired: int = 0

    def acquire(self) -> FakePoolConnectionManager:
        self.acquired += 1
        return FakePoolConnectionManager(self.connection)


def _dependencies(
    **overrides: object,
) -> composition.FaqWorkbenchParallelProcessingDependencies:
    values = {
        "id_factory": FakeIdFactory(),
        "claim_observations_runner": FakeClaimObservationsRunner(),
        "canonicalization_barrier_service": FakeCanonicalizationBarrierService(),
        "registry_application_service": FakeRegistryApplicationService(),
        "llm_json_invocation": FakeLlmJsonInvocation(),
        "registry_merge_prompt_path": Path(
            "src/agent/prompts/faq_surface_registry_merge.ru.txt"
        ),
    }
    values.update(overrides)
    return composition.FaqWorkbenchParallelProcessingDependencies(**values)


def test_parallel_processing_composition_imports_current_boundary_without_legacy_runner() -> (
    None
):
    loader = composition.__loader__
    assert isinstance(loader, importlib.abc.InspectLoader)
    source = loader.get_source(composition.__name__)
    assert source is not None

    assert "FaqWorkbenchParallelSectionProcessorAdapter" in source
    assert "FaqWorkbenchParallelRegistryApplicationProcessorAdapter" in source
    assert "FaqWorkbenchCanonicalizationBarrierProcessorAdapter" in source
    assert "make_workbench_canonicalization_barrier_service_from_repository" in source

    assert "FaqWorkbenchClaimObservationsRunner" not in source
    assert "ProcessMarkdownDocumentCommand" not in source
    assert "candidate_fact_sets" not in source
    assert "match_context" not in source


def test_parallel_processing_composition_builds_coordinator_with_section_registry_and_barrier_adapters() -> (
    None
):
    coordinator = (
        composition.make_workbench_parallel_processing_coordinator_from_repository(
            repository=FakeRepository(),
            dependencies=_dependencies(),
        )
    )

    assert coordinator._section_processor.__class__.__name__ == (
        "FaqWorkbenchParallelSectionProcessorAdapter"
    )
    assert coordinator._registry_processor.__class__.__name__ == (
        "FaqWorkbenchParallelRegistryApplicationProcessorAdapter"
    )
    assert coordinator._canonicalization_barrier_processor.__class__.__name__ == (
        "FaqWorkbenchCanonicalizationBarrierProcessorAdapter"
    )

    section_adapter = coordinator._section_processor
    assert section_adapter.processor.claim_observations_runner.__class__ is (
        FakeClaimObservationsRunner
    )
    assert section_adapter.processor.id_factory.__class__ is FakeIdFactory

    barrier_adapter = coordinator._canonicalization_barrier_processor
    assert (
        barrier_adapter.barrier_service.__class__ is FakeCanonicalizationBarrierService
    )


def test_parallel_processing_composition_allows_unwired_barrier_only_explicitly() -> (
    None
):
    coordinator = (
        composition.make_workbench_parallel_processing_coordinator_from_repository(
            repository=FakeRepository(),
            dependencies=_dependencies(canonicalization_barrier_service=None),
        )
    )

    assert coordinator._canonicalization_barrier_processor is None


def test_parallel_processing_composition_requires_claim_observations_runner() -> None:
    with pytest.raises(DomainInvariantError, match="claim_observations_runner"):
        composition.make_workbench_parallel_processing_coordinator_from_repository(
            repository=FakeRepository(),
            dependencies=_dependencies(claim_observations_runner=None),
        )


@pytest.mark.asyncio
async def test_parallel_processing_pool_factory_uses_connection_and_builds_coordinator(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeKnowledgeWorkbenchRepository:
        def __init__(self, connection: object) -> None:
            captured["connection"] = connection

    monkeypatch.setattr(
        composition,
        "KnowledgeWorkbenchRepository",
        FakeKnowledgeWorkbenchRepository,
    )

    pool = FakePool(connection=object())
    coordinator = await composition.make_workbench_parallel_processing_coordinator(
        pool=pool,
        dependencies=_dependencies(),
    )

    assert pool.acquired == 1
    assert captured["connection"] is pool.connection
    assert coordinator._canonicalization_barrier_processor is not None


def test_section_processor_builder_keeps_prompt_c_out_of_section_worker_composition() -> (
    None
):
    section_processor = composition.make_workbench_section_processor_from_repository(
        repository=FakeRepository(),
        dependencies=_dependencies(),
    )

    assert section_processor.claim_observations_runner.__class__ is (
        FakeClaimObservationsRunner
    )
    assert not hasattr(section_processor, "registry_merge_generator")
    assert not hasattr(section_processor, "registry_merge_service")


def test_full_canonicalization_barrier_factory_builds_prompt_c_dependency_graph() -> (
    None
):
    barrier = (
        composition.make_workbench_canonicalization_barrier_service_from_repository(
            repository=FakeRepository(),
            dependencies=_dependencies(canonicalization_barrier_service=None),
        )
    )

    assert barrier.__class__.__name__ == "FaqWorkbenchCanonicalizationBarrierService"
    assert barrier._local_claim_retrieval_service.__class__.__name__ == (
        "FaqWorkbenchLocalClaimRetrievalService"
    )
    assert barrier._local_claim_retrieval_service.graph_loader.__class__.__name__ == (
        "FaqWorkbenchLocalClaimGraphLoaderService"
    )
    assert barrier._registry_merge_generator.__class__.__name__ == (
        "FaqWorkbenchRegistryMergeGenerator"
    )
    assert (
        barrier._registry_merge_generator.llm_invocation.__class__
        is FakeLlmJsonInvocation
    )
    assert barrier._registry_merge_generator.config.prompt_path == Path(
        "src/agent/prompts/faq_surface_registry_merge.ru.txt"
    )
    assert barrier._registry_merge_service.__class__.__name__ == (
        "FaqWorkbenchRegistryMergeService"
    )
    assert barrier._registry_application_service.__class__ is (
        FakeRegistryApplicationService
    )


def test_full_canonicalization_barrier_factory_does_not_leak_prompt_c_into_section_worker() -> (
    None
):
    loader = composition.__loader__
    assert isinstance(loader, importlib.abc.InspectLoader)
    source = loader.get_source(composition.__name__)
    assert source is not None
    section_factory_source = source.split(
        "def make_workbench_section_processor_from_repository",
        1,
    )[1].split(
        "def make_workbench_canonicalization_barrier_service_from_repository",
        1,
    )[0]

    assert "claim_observations_runner" in section_factory_source
    assert "FaqWorkbenchRegistryMergeGenerator" not in section_factory_source
    assert "FaqWorkbenchCanonicalizationBarrierService" not in section_factory_source
