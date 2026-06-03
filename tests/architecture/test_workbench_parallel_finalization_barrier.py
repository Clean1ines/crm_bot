from __future__ import annotations

import ast
from pathlib import Path


ORCH = Path("src/application/services/faq_workbench_document_processing_orchestrator.py")
COORDINATOR = Path(
    "src/application/services/faq_workbench_parallel_processing_coordinator_service.py"
)
DOMAIN = Path("src/domain/project_plane/knowledge_workbench/parallel_drain_policy.py")
PORT = Path("src/application/ports/knowledge_workbench.py")


def _read(path: Path) -> str:
    assert path.exists(), f"missing expected file: {path}"
    return path.read_text(encoding="utf-8")


def _method_source(path: Path, method_name: str) -> str:
    source = _read(path)
    tree = ast.parse(source, filename=str(path))
    lines = source.splitlines()

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == method_name:
            if node.end_lineno is None:
                raise AssertionError(f"{method_name} has no end line")
            return "\n".join(lines[node.lineno - 1 : node.end_lineno])

    raise AssertionError(f"{method_name} not found in {path}")


def test_parallel_finalization_domain_policy_exists() -> None:
    domain = _read(DOMAIN)
    port = _read(PORT)

    assert "ParallelDrainWorkCounts" in domain
    assert "ParallelFinalizationDecision" in domain
    assert "decide_parallel_finalization" in domain
    assert "ensure_parallel_processing_can_finalize" in domain

    assert "get_parallel_processing_drain_counts" in port


def test_final_reconciliation_and_materialization_are_guarded_by_parallel_drain_barrier() -> None:
    helper_source = _method_source(ORCH, "_ensure_parallel_finalization_ready")

    assert "get_parallel_processing_drain_counts" in helper_source
    assert "ensure_parallel_processing_can_finalize" in helper_source

    for method_name in (
        "process_markdown_document",
        "process_existing_document_sections",
    ):
        method_source = _method_source(ORCH, method_name)

        assert "_ensure_parallel_finalization_ready(" in method_source
        assert "_persist_final_reconciliation_advice(" in method_source
        assert "materialize_surfaces(" in method_source

        barrier_index = method_source.index("_ensure_parallel_finalization_ready(")
        reconciliation_index = method_source.index("_persist_final_reconciliation_advice(")
        materialization_index = method_source.index("materialize_surfaces(")

        assert barrier_index < reconciliation_index
        assert barrier_index < materialization_index


def test_parallel_finalization_barrier_does_not_detour_into_legacy_resume_or_flags() -> None:
    combined = _read(ORCH) + "\n" + _read(COORDINATOR) + "\n" + _read(DOMAIN)

    forbidden = (
        "ENABLE_WORKBENCH_PARALLEL",
        "WORKBENCH_PARALLEL_ENABLED",
        "os.getenv",
        "resume_workbench",
        "cancel_workbench",
        "stop_workbench",
        "knowledge_surface_compiler",
        "knowledge_surface_parallel_graph_compiler",
        "process_knowledge_upload",
        "AnswerCandidate",
        "CandidateCluster",
        "KnowledgeSurfaceCompilerPort",
    )
    for marker in forbidden:
        assert marker not in combined
