from __future__ import annotations

from pathlib import Path


COMPOSITION = Path("src/interfaces/composition/faq_workbench_parallel_processing.py")
HANDLER = Path("src/infrastructure/queue/handlers/workbench_parallel_processing.py")
COORDINATOR = Path(
    "src/application/services/faq_workbench_parallel_processing_coordinator_service.py"
)
REPOSITORY = Path("src/infrastructure/db/knowledge_workbench_repository.py")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_parallel_composition_dependencies_carry_lifecycle_and_durable_drain_ports() -> None:
    source = _read(COMPOSITION)
    dependency_block = source.split(
        "class FaqWorkbenchParallelProcessingDependencies",
        1,
    )[1].split(
        "async def make_workbench_parallel_processing_coordinator",
        1,
    )[0]

    assert "drain_counts_provider: object | None = None" in dependency_block
    assert "lifecycle_completion_port: object | None = None" in dependency_block


def test_parallel_composition_passes_lifecycle_and_durable_drain_ports_into_coordinator() -> None:
    source = _read(COMPOSITION)
    factory = source.split(
        "def make_workbench_parallel_processing_coordinator_from_repository",
        1,
    )[1].split(
        "async def make_workbench_section_work_item_processor",
        1,
    )[0]

    assert "drain_counts_provider=" in factory
    assert "lifecycle_completion_port=" in factory
    assert "dependencies.drain_counts_provider" in factory
    assert "dependencies.lifecycle_completion_port" in factory
    assert "else repository" in factory


def test_parallel_queue_handler_wires_repository_as_lifecycle_and_durable_drain_provider() -> None:
    source = _read(HANDLER)
    dependency_factory = source.split(
        "def make_workbench_parallel_processing_dependencies",
        1,
    )[1].split(
        "def make_workbench_parallel_processing_coordinator",
        1,
    )[0]

    assert dependency_factory.count("drain_counts_provider=repository") >= 2
    assert dependency_factory.count("lifecycle_completion_port=repository") >= 2


def test_repository_supports_lifecycle_completion_and_durable_drain_methods_used_by_coordinator() -> None:
    coordinator = _read(COORDINATOR)
    repository = _read(REPOSITORY)

    assert "drain_counts_provider" in coordinator
    assert "lifecycle_completion_port" in coordinator
    assert "get_parallel_processing_drain_counts" in repository
    assert "mark_parallel_processing_completed" in repository
