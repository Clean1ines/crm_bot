from __future__ import annotations

import pytest

from src.application.services.faq_workbench_document_processing_orchestrator import (
    FaqWorkbenchDocumentProcessingOrchestrator,
    FaqWorkbenchDocumentProcessingResult,
    RetiredSequentialWorkbenchOrchestratorError,
)


@pytest.mark.asyncio
async def test_sequential_workbench_orchestrator_is_retired_shell() -> None:
    orchestrator = FaqWorkbenchDocumentProcessingOrchestrator()

    with pytest.raises(
        RetiredSequentialWorkbenchOrchestratorError,
        match="Sequential FAQ Workbench orchestrator is retired",
    ):
        await orchestrator.process_existing_document(
            project_id="project-1",
            document_id="document-1",
            processing_run_id="processing-run-1",
        )


def test_retired_orchestrator_result_defaults_document_cutover_reason() -> None:
    result = FaqWorkbenchDocumentProcessingResult(
        document_id="document-1",
        processing_run_id="processing-run-1",
    )

    assert result.document_id == "document-1"
    assert result.processing_run_id == "processing-run-1"
    assert result.processed is False
    assert result.reason == "retired_sequential_orchestrator"


def test_orchestrator_module_does_not_export_old_sequential_commands() -> None:
    import src.application.services.faq_workbench_document_processing_orchestrator as module

    assert not hasattr(module, "Process" + "Markdown" + "Document" + "Command")
    assert not hasattr(
        module, "Process" + "Existing" + "Document" + "Sections" + "Command"
    )
    assert not hasattr(module, "Claim" + "Observations" + "Input")
    assert not hasattr(module, "Workbench" + "Processing" + "Cancelled" + "Error")


def test_orchestrator_source_points_to_parallel_workbench_processing() -> None:
    from pathlib import Path

    source = Path(
        "src/application/services/faq_workbench_document_processing_orchestrator.py"
    ).read_text(encoding="utf-8")

    assert "Retired compatibility shell" in source
    assert "parallel section queue" in source
    assert "use parallel Workbench processing" in source

    assert "process_markdown_document" not in source
    assert "process_existing_document_sections" not in source
    assert "Registry" + "Update" + "Proposal" not in source
    assert "claim" + "_inputs" not in source
    assert "candidate" + "_fact_sets" not in source
    assert "match" + "_context" not in source
