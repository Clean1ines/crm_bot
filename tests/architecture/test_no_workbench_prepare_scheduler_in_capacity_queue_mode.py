from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_capacity_runtime_core_files_exist() -> None:
    expected_paths = (
        "src/contexts/capacity_admission_queue/application/ports/"
        "capacity_lane_claim_repository_port.py",
        "src/contexts/capacity_admission_queue/application/ports/"
        "capacity_window_budget_repository_port.py",
        "src/contexts/capacity_admission_queue/infrastructure/postgres/"
        "postgres_capacity_lane_claim_repository.py",
        "src/contexts/capacity_admission_queue/infrastructure/postgres/"
        "postgres_capacity_window_budget_repository.py",
        "src/contexts/capacity_admission_queue/application/run_capacity_window_drain.py",
        "src/contexts/capacity_admission_queue/application/"
        "run_capacity_lane_drain_for_available_windows.py",
        "migrations/119_create_capacity_window_budget_state.sql",
    )

    for relative_path in expected_paths:
        assert (ROOT / relative_path).exists()


def test_active_llm_dispatch_cutover_is_disabled_until_strategies_exist() -> None:
    from src.contexts.knowledge_workbench.application.sagas.llm_dispatch_ownership import (
        CAPACITY_QUEUE_RUNTIME_CORE_ENABLED,
        CAPACITY_QUEUE_OWNS_LLM_DISPATCH,
    )

    assert CAPACITY_QUEUE_RUNTIME_CORE_ENABLED is True
    assert CAPACITY_QUEUE_OWNS_LLM_DISPATCH is False


def test_schedule_path_keeps_legacy_prepare_when_cutover_disabled() -> None:
    source = (
        ROOT / "src/contexts/knowledge_workbench/application/sagas/"
        "handle_schedule_claim_builder_section_work_command.py"
    ).read_text(encoding="utf-8")

    assert "if not CAPACITY_QUEUE_OWNS_LLM_DISPATCH:" in source
    assert "append_pending_command(\n                next_command," in source


def test_reconcile_paths_keep_legacy_prepare_functions_under_legacy_mode() -> None:
    for relative_path in (
        "src/contexts/knowledge_workbench/application/sagas/"
        "handle_reconcile_claim_builder_progress_command.py",
        "src/contexts/knowledge_workbench/application/sagas/"
        "handle_reconcile_draft_claim_compaction_progress_command.py",
    ):
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        assert "if CAPACITY_QUEUE_OWNS_LLM_DISPATCH and decision in {" in source
        assert "return _prepare_dispatch_batch_command(" in source


def test_dispatcher_does_not_block_legacy_prepare_while_cutover_disabled() -> None:
    source = (
        ROOT / "src/contexts/knowledge_workbench/application/sagas/"
        "dispatch_knowledge_extraction_workflow_command.py"
    ).read_text(encoding="utf-8")

    assert "capacity_queue_owns_llm_dispatch_legacy_prepare_blocked" not in source
    assert "CAPACITY_QUEUE_OWNS_LLM_DISPATCH_BLOCKED_LEGACY_PREPARE" not in source
