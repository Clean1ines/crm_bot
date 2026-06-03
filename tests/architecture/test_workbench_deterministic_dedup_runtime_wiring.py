from __future__ import annotations

from pathlib import Path


PROCESSOR = Path(
    "src/application/services/faq_workbench_section_work_item_processor_service.py"
)
DEDUP_SERVICE = Path(
    "src/application/services/faq_workbench_deterministic_dedup_service.py"
)


def _read(path: Path) -> str:
    assert path.exists(), f"missing expected file: {path}"
    return path.read_text(encoding="utf-8")


def test_section_work_item_processor_wires_deterministic_dedup_boundary_before_registry_queue() -> None:
    processor = _read(PROCESSOR)
    dedup_service = _read(DEDUP_SERVICE)

    assert "class FaqWorkbenchDeterministicDedupService" in dedup_service
    assert "PersistDeterministicDedupNodeOutputCommand" in dedup_service
    assert "persist_deterministic_dedup_output" in dedup_service

    assert "FaqWorkbenchDeterministicDedupService" in processor
    assert "PersistDeterministicDedupNodeOutputCommand" in processor
    assert "persist_deterministic_dedup_output" in processor

    dedup_index = processor.index("persist_deterministic_dedup_output")
    registry_queue_index = processor.index("RegistryApplicationQueueItem(")

    assert dedup_index < registry_queue_index

    forbidden = (
        "LlmJsonInvocationRequest",
        "generate_registry_merge",
        "generate_claim_observations",
        "create_registry_snapshot",
        "upsert_question_registry_entries",
        "RegistryUpdateAppliedBy.LLM_ADVISORY",
    )
    for marker in forbidden:
        assert marker not in processor
