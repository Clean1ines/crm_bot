from __future__ import annotations

from pathlib import Path


REPOSITORY = Path("src/infrastructure/db/knowledge_workbench_repository.py")
PORT = Path("src/application/ports/knowledge_workbench.py")
BARRIER = Path("src/application/services/faq_workbench_canonicalization_barrier_service.py")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_fact_registry_canonicalization_completion_guard_is_declared_in_ports_and_used_by_barrier() -> None:
    port = _read(PORT)
    barrier = _read(BARRIER)

    assert "has_completed_fact_registry_canonicalization" in port
    assert "has_completed_fact_registry_canonicalization" in barrier
    assert "already_canonicalized" in barrier


def test_fact_registry_canonicalization_completion_guard_uses_completed_parsed_prompt_c_artifact() -> None:
    source = _read(REPOSITORY)

    assert "async def has_completed_fact_registry_canonicalization" in source
    assert "knowledge_workbench_processing_node_artifacts" in source
    assert "knowledge_workbench_processing_node_runs" in source
    assert "artifact.metadata ->> 'contract' = 'fact_registry_canonicalization'" in source
    assert "artifact.artifact_type = 'parsed_llm_output'" in source
    assert "node_run.node_name = 'faq_surface_registry_merge'" in source
    assert "node_run.status = 'completed'" in source
    assert "artifact.section_id IS NULL" in source
    assert "node_run.section_id IS NULL" in source


def test_fact_registry_canonicalization_completion_guard_does_not_use_raw_artifact_or_section_prompt_a() -> None:
    source = _read(REPOSITORY)
    method_source = source.split(
        "async def has_completed_fact_registry_canonicalization",
        1,
    )[1].split(
        "async def get_parallel_processing_drain_counts",
        1,
    )[0]

    assert "raw_llm_output" not in method_source
    assert "claim_observations" not in method_source
    assert "faq_surface_claim_observations" not in method_source
    assert "artifact_type = 'raw_llm_output'" not in method_source
