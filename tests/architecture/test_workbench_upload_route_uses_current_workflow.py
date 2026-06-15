from __future__ import annotations

import importlib
from pathlib import Path


def test_workbench_upload_route_imports_current_workflow_factory_and_command() -> None:
    composition = importlib.import_module(
        "src.interfaces.composition.knowledge_extraction_after_upload_composition",
    )
    workflow = importlib.import_module(
        "src.interfaces.composition.knowledge_extraction_workflow_after_upload",
    )
    route_module = importlib.import_module("src.interfaces.http.knowledge")

    assert callable(composition.make_knowledge_extraction_workflow_after_upload)
    assert workflow.RunKnowledgeExtractionWorkflowAfterUploadCommand is not None
    assert callable(route_module.make_knowledge_extraction_workflow_after_upload)
    assert route_module.RunKnowledgeExtractionWorkflowAfterUploadCommand is (
        workflow.RunKnowledgeExtractionWorkflowAfterUploadCommand
    )


def test_workbench_upload_route_uses_split_imports_from_real_modules() -> None:
    source = Path("src/interfaces/http/knowledge.py").read_text(encoding="utf-8")

    assert (
        "from src.interfaces.composition.knowledge_extraction_after_upload_composition import ("
        in source
    )
    assert "    make_knowledge_extraction_workflow_after_upload," in source
    assert (
        "from src.interfaces.composition.knowledge_extraction_workflow_after_upload import ("
        in source
    )
    assert "    RunKnowledgeExtractionWorkflowAfterUploadCommand," in source

    broken_combined_import = (
        "from src.interfaces.composition.knowledge_extraction_after_upload_composition "
        "import (\\n    RunKnowledgeExtractionWorkflowAfterUploadCommand"
    )
    assert broken_combined_import not in source


def test_workbench_upload_route_does_not_use_retired_legacy_upload_path() -> None:
    source = Path("src/interfaces/http/knowledge.py").read_text(encoding="utf-8")

    forbidden = (
        "faq_workbench_document_cards",
        "knowledge_entries",
        "knowledge_source_chunks",
        "knowledge_retrieval_surface",
        "KnowledgeService.upload",
        "TASK_PROCESS_KNOWLEDGE_UPLOAD",
        "chunker_factory=make_chunker",
        "knowledge_repo_factory=make_knowledge_repo",
        "preprocessor_factory=make_knowledge_preprocessor",
    )

    for marker in forbidden:
        assert marker not in source


def test_workbench_upload_route_keeps_workflow_only_command_path() -> None:
    source = Path("src/interfaces/http/knowledge.py").read_text(encoding="utf-8")

    required = (
        "RunSourceIngestionFirstPhaseCommand",
        "RunKnowledgeExtractionWorkflowAfterUploadCommand",
        "make_knowledge_extraction_workflow_after_upload",
        "workflow_runner = make_knowledge_extraction_workflow_after_upload",
        "await workflow_runner.execute(",
        "source_document_ref",
        "source_unit_count",
        "draft_claims_url",
    )

    for marker in required:
        assert marker in source
