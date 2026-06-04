from __future__ import annotations

from pathlib import Path


def test_parallel_coordinator_checks_integrity_before_marking_success() -> None:
    source = Path(
        "src/application/services/faq_workbench_parallel_processing_coordinator_service.py"
    ).read_text()

    assert "ParallelProcessingIntegrityCounts" in source
    assert "ParallelProcessingIntegrityError" in source
    assert "get_parallel_processing_integrity_counts" in source
    assert "await self._assert_parallel_processing_integrity(command)" in source
    assert "mark_parallel_processing_completed" in source

    integrity_call_index = source.index(
        "await self._assert_parallel_processing_integrity(command)"
    )
    completion_call_index = source.index(
        "await self._lifecycle_completion_port.mark_parallel_processing_completed"
    )
    assert integrity_call_index < completion_call_index


def test_repository_exposes_parallel_processing_integrity_counts() -> None:
    source = Path("src/infrastructure/db/knowledge_workbench_repository.py").read_text()

    assert "async def get_parallel_processing_integrity_counts(" in source
    assert "knowledge_workbench_document_sections" in source
    assert "knowledge_workbench_section_batch_queue_items" in source
    assert "faq_surface_claim_observations" in source
    assert "faq_surface_registry_merge" in source


def test_parallel_composition_wires_repository_as_integrity_counts_provider() -> None:
    source = Path(
        "src/interfaces/composition/faq_workbench_parallel_processing.py"
    ).read_text()

    assert "integrity_counts_provider=(" in source
    assert "dependencies.integrity_counts_provider" in source
    assert "else repository" in source
    assert "drain_counts_provider=(" in source
    assert "dependencies.drain_counts_provider" in source
