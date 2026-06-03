from __future__ import annotations

import ast
from pathlib import Path


PRODUCTION_ROOTS = (
    Path("src/infrastructure/queue"),
    Path("src/interfaces/composition"),
    Path("src/interfaces/http"),
    Path("src/interfaces/telegram"),
    Path("src/application/workbench"),
    Path("src/application/workbench_commands"),
    Path("src/application/workbench_observability"),
)

LEGACY_IMPORT_TOKENS = (
    "faq_workbench_document_processing_orchestrator",
    "FaqWorkbenchDocumentProcessingOrchestrator",
    "faq_workbench_final_reconciliation_generator",
    "FaqWorkbenchFinalReconciliation",
    "faq_workbench_final_reconciliation_service",
    "faq_workbench_surface_materialization_service",
    "MaterializeRegistrySurfacesCommand",
    "ApplyRegistryFindingsCommand",
    "ApplyRegistryFindingsResult",
)


def _python_files() -> list[Path]:
    files: list[Path] = []
    for root in PRODUCTION_ROOTS:
        assert root.exists(), f"missing production root: {root}"
        files.extend(path for path in root.rglob("*.py") if path.is_file())
    return sorted(files)


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            names = ", ".join(alias.name for alias in node.names)
            imports.append(f"from {module} import {names}")
        elif isinstance(node, ast.Import):
            imports.append("import " + ", ".join(alias.name for alias in node.names))

    return imports


def test_production_runtime_does_not_import_retired_sequential_workbench_graph() -> None:
    offenders: list[str] = []

    for path in _python_files():
        for statement in _imports(path):
            for token in LEGACY_IMPORT_TOKENS:
                if token in statement:
                    offenders.append(f"{path}: {statement}")

    assert offenders == []


def test_legacy_workbench_document_handler_is_guard_only_not_orchestrator_wiring() -> None:
    source = Path("src/infrastructure/queue/handlers/workbench_document.py").read_text(
        encoding="utf-8"
    )

    assert "legacy process_workbench_document task is retired" in source
    assert "PermanentJobError" in source

    forbidden = (
        "FaqWorkbenchDocumentProcessingOrchestrator",
        "make_workbench_document_processing_orchestrator",
        "make_workbench_final_reconciliation_generator",
        "ApplyRegistryFindingsCommand",
        "apply_findings_to_registry",
        "MaterializeRegistrySurfacesCommand",
        "surface_materialization",
    )

    for token in forbidden:
        assert token not in source


def test_parallel_workbench_handler_is_the_reachable_processing_runtime() -> None:
    source = Path(
        "src/infrastructure/queue/handlers/workbench_parallel_processing.py"
    ).read_text(encoding="utf-8")

    assert "handle_workbench_parallel_processing_job_from_connection" in source
    assert "make_workbench_parallel_processing_coordinator" in source
    assert "run_parallel_processing" in source


def test_upload_path_uses_parallel_queue_not_legacy_document_queue() -> None:
    source = Path("src/interfaces/composition/faq_workbench_upload.py").read_text(
        encoding="utf-8"
    )

    assert "WorkbenchParallelQueueAdapter" in source
    assert "WorkbenchQueueAdapter" not in source
