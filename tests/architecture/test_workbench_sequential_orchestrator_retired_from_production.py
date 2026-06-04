from pathlib import Path


HANDLER = Path("src/infrastructure/queue/handlers/workbench_document.py")
DISPATCHER = Path("src/infrastructure/queue/job_dispatcher.py")
UPLOAD = Path("src/interfaces/composition/faq_workbench_upload.py")
PARALLEL_HANDLER = Path(
    "src/infrastructure/queue/handlers/workbench_parallel_processing.py"
)


def _read(path: Path) -> str:
    assert path.exists(), f"missing expected source file: {path}"
    return path.read_text(encoding="utf-8")


def test_upload_uses_parallel_queue_adapter_not_legacy_document_queue_adapter() -> None:
    source = _read(UPLOAD)

    assert "WorkbenchParallelQueueAdapter" in source
    assert "WorkbenchQueueAdapter" not in source


def test_legacy_process_workbench_document_handler_is_permanent_guard_only() -> None:
    source = _read(HANDLER)

    assert "legacy process_workbench_document task is retired" in source
    assert "PermanentJobError" in source

    forbidden = (
        "FaqWorkbenchDocumentProcessingOrchestrator",
        "process_existing_document_sections",
        "ApplyRegistryFindingsCommand",
        "apply_findings_to_registry",
        "MaterializeRegistrySurfacesCommand",
        "FinalReconciliation",
        "final_reconciliation",
        "surface_materialization",
        "make_workbench_document_processing_orchestrator",
        "make_workbench_final_reconciliation_generator",
    )

    for token in forbidden:
        assert token not in source


def test_parallel_handler_remains_the_real_workbench_processing_runtime() -> None:
    source = _read(PARALLEL_HANDLER)

    assert "make_workbench_parallel_processing_coordinator" in source
    assert "handle_workbench_parallel_processing_job_from_connection" in source
    assert "run_parallel_processing" in source


def test_dispatcher_still_handles_parallel_workbench_task() -> None:
    source = _read(DISPATCHER)

    assert "TASK_PROCESS_WORKBENCH_PARALLEL_PROCESSING" in source
    assert "handle_workbench_parallel_processing_job_from_connection" in source
