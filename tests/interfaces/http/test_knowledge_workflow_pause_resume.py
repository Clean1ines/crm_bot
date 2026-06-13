from __future__ import annotations

from pathlib import Path


def test_http_pause_endpoint_uses_project_access_and_pause_composition() -> None:
    source = Path("src/interfaces/http/knowledge.py").read_text(encoding="utf-8")

    assert '@router.post("/workflows/{workflow_run_id}/pause")' in source
    assert "await _require_project_access(" in source
    assert "make_pause_knowledge_extraction_workflow(pool=pool)" in source
    assert "PauseKnowledgeExtractionWorkflowCommand(" in source
    assert "source_ingestion_command" not in _function_source(
        source,
        "async def pause_knowledge_extraction_workflow",
    )


def test_http_resume_endpoint_unpauses_then_drains_current_workflow_vertical() -> None:
    source = Path("src/interfaces/http/knowledge.py").read_text(encoding="utf-8")
    resume_source = _function_source(
        source,
        "async def resume_knowledge_extraction_workflow",
    )

    assert '@router.post("/workflows/{workflow_run_id}/resume")' in source
    assert "make_resume_knowledge_extraction_workflow_transition(pool=pool)" in source
    assert "make_knowledge_extraction_workflow_resume(" in resume_source
    assert "RunKnowledgeExtractionWorkflowResumeCommand(" in resume_source
    assert "document_id=workflow_run_id" in resume_source
    assert "RunSourceIngestionFirstPhaseCommand" not in resume_source
    assert "get_queue_repo" not in resume_source


def _function_source(source: str, function_marker: str) -> str:
    start = source.index(function_marker)
    next_route = source.find("\n\n@router.", start + len(function_marker))
    if next_route == -1:
        return source[start:]
    return source[start:next_route]
