from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_execution_runtime_postgres_payload_readers_use_bounded_jsonb_hydration() -> (
    None
):
    files = [
        "src/contexts/execution_runtime/infrastructure/postgres/"
        "postgres_work_item_lease_repository.py",
        "src/contexts/execution_runtime/infrastructure/postgres/"
        "postgres_work_item_attempt_dispatch_read_repository.py",
    ]

    for file_path in files:
        source = _read(file_path)
        assert "hydrate_jsonb_object_payload" in source
        assert "payload must be Mapping" not in source
        assert "if not isinstance(payload, Mapping)" not in source
        assert "dispatch_payload must be Mapping" not in source
        assert "schedule_payload must be Mapping" not in source


def test_knowledge_workbench_extraction_p0_payload_readers_use_bounded_jsonb_hydration() -> (
    None
):
    files = [
        "src/contexts/knowledge_workbench/extraction/infrastructure/postgres/"
        "postgres_claim_builder_retry_action_read_repository.py",
        "src/contexts/knowledge_workbench/extraction/infrastructure/postgres/"
        "postgres_draft_claim_cluster_preview_repository.py",
    ]

    for file_path in files:
        source = _read(file_path)
        assert "hydrate_jsonb_object_payload" in source
        assert "payload must be Mapping" not in source


def test_jsonb_hydration_helpers_are_bounded_not_generic_utils() -> None:
    assert (
        ROOT / "src/contexts/execution_runtime/infrastructure/postgres/"
        "jsonb_payload_hydration.py"
    ).exists()
    assert (
        ROOT / "src/contexts/knowledge_workbench/extraction/infrastructure/postgres/"
        "jsonb_payload_hydration.py"
    ).exists()

    assert not (
        ROOT / "src/contexts/execution_runtime/infrastructure/postgres/utils.py"
    ).exists()
    assert not (
        ROOT
        / "src/contexts/knowledge_workbench/extraction/infrastructure/postgres/utils.py"
    ).exists()
