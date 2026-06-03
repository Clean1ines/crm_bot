from __future__ import annotations

import ast
from pathlib import Path


ORCH = Path(
    "src/application/services/faq_workbench_document_processing_orchestrator.py"
)
AUDIT = Path("tests/architecture/test_workbench_graph_runtime_coverage_audit.py")


def _read(path: Path) -> str:
    assert path.exists(), f"missing expected source file: {path}"
    return path.read_text(encoding="utf-8")


def _function_source(path: Path, function_name: str) -> str:
    source = _read(path)
    tree = ast.parse(source, filename=str(path))
    lines = source.splitlines(keepends=True)

    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == function_name
        ):
            assert node.end_lineno is not None
            return "".join(lines[node.lineno - 1 : node.end_lineno])

    raise AssertionError(f"{function_name} not found in {path}")


def test_orchestrator_has_single_section_batch_checkpoint_path() -> None:
    source = _read(ORCH)

    assert "FaqWorkbenchSectionBatchPlanningService" in source
    assert "ProcessParallelSectionBatchCommand" in source
    assert "async def _process_parallel_section_batch_checkpoint(" in source
    assert "_section_batch_planning_service.process_parallel_section_batch" in source

    assert "PlanParallelSectionBatchCommand" not in source
    assert "async def _persist_section_batch_checkpoint(" not in source


def test_markdown_processing_persists_section_batch_checkpoint_before_section_loop() -> (
    None
):
    source = _function_source(ORCH, "process_markdown_document")

    checkpoint_index = source.index(
        "await self._process_parallel_section_batch_checkpoint("
    )
    processing_index = source.index("await self._process_sections_against_registry(")

    assert checkpoint_index < processing_index
    assert "sections=upload.sections" in source
    assert "latest_registry_snapshot=upload.initial_snapshot" in source
    assert "sections=sections_to_process" in source


def test_existing_processing_restores_then_persists_batch_checkpoint_before_section_loop() -> (
    None
):
    source = _function_source(ORCH, "process_existing_document_sections")

    restore_index = source.index("_restore_checkpoint_service.restore_checkpoint(")
    checkpoint_index = source.index(
        "await self._process_parallel_section_batch_checkpoint("
    )
    processing_index = source.index("await self._process_sections_against_registry(")

    assert restore_index < checkpoint_index < processing_index
    assert "sections=restore_checkpoint.pending_sections" in source
    assert "latest_registry_snapshot=command.latest_registry_snapshot" in source
    assert "sections=existing_sections_to_process" in source


def test_section_batch_checkpoint_is_not_real_parallel_executor_yet() -> None:
    source = _function_source(ORCH, "_process_parallel_section_batch_checkpoint")

    forbidden = (
        "asyncio.gather",
        "asyncio.create_task",
        "TaskGroup",
        "ThreadPoolExecutor",
        "ProcessPoolExecutor",
        "lease_section_batch_queue_item",
        "worker_loop",
    )
    for marker in forbidden:
        assert marker not in source


def test_section_batch_checkpoint_does_not_detour_into_resume_cancel_stop() -> None:
    source = _function_source(ORCH, "_process_parallel_section_batch_checkpoint")

    forbidden = (
        "resume_workbench",
        "cancel_workbench",
        "stop_workbench",
        "ensure_document_can_be_resumed",
        "decide_processing_cancel_transition",
        "decide_processing_resume_or_recovery_transition",
    )
    for marker in forbidden:
        assert marker not in source


def test_runtime_coverage_audit_matches_checkpoint_not_done_state() -> None:
    source = _read(AUDIT)

    assert "SECTION_BATCH_PLANNING_SERVICE" in source
    assert "PROCESS_PARALLEL_SECTION_BATCH" in source
    assert "Section batch plan/work-item checkpoint is wired" in source
    assert "No real parallel worker leasing" in source
    assert (
        "single-writer registry application queue execution is not yet connected"
        in source
    )

    connected_nodes_test = _function_source(
        AUDIT,
        "test_runtime_connected_nodes_are_the_only_nodes_claimed_as_done",
    )
    assert '"PROCESS_PARALLEL_SECTION_BATCH"' not in connected_nodes_test
