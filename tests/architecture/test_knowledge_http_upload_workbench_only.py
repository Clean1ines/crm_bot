from __future__ import annotations

import ast
import importlib
from pathlib import Path


def test_knowledge_upload_http_boundary_is_workbench_only() -> None:
    source = Path("src/interfaces/http/knowledge.py").read_text(encoding="utf-8")

    assert "RunSourceIngestionFirstPhaseCommand" in source
    assert "RunKnowledgeExtractionWorkflowAfterUploadCommand" in source
    assert "make_knowledge_extraction_workflow_after_upload" in source
    assert "Only FAQ Workbench uploads are supported" in source

    forbidden = (
        "src.interfaces.composition.knowledge_upload",
        "upload_knowledge_file",
        "KnowledgeService(",
        "process_knowledge_upload",
        "TASK_PROCESS_KNOWLEDGE_UPLOAD",
        "ScheduleClaimBuilderSectionWork(",
    )
    for marker in forbidden:
        assert marker not in source


def test_non_faq_upload_modes_fail_closed_until_workbench_analog_exists() -> None:
    source = Path("src/interfaces/http/knowledge.py").read_text(encoding="utf-8")
    module = ast.parse(source)

    upload_nodes = [
        node
        for node in module.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "upload_knowledge"
    ]
    assert len(upload_nodes) == 1

    upload_source = ast.get_source_segment(source, upload_nodes[0])
    assert upload_source is not None

    assert "require_faq_workbench_mode" in upload_source
    assert "status_code=400" in upload_source
    assert "Only FAQ Workbench uploads are supported by this endpoint" in upload_source
    assert "status_code=422" not in upload_source

    globally_forbidden = (
        "mode != MODE_FAQ",
        "normalize_preprocessing_mode",
        "src.domain.project_plane.knowledge_preprocessing",
    )
    for marker in globally_forbidden:
        assert marker not in source


def test_knowledge_http_module_imports_without_legacy_upload_path() -> None:
    module = importlib.import_module("src.interfaces.http.knowledge")

    assert module is not None


def test_knowledge_upload_http_boundary_uses_workflow_after_upload_runner() -> None:
    source = Path("src/interfaces/http/knowledge.py").read_text(encoding="utf-8")

    assert "RunSourceIngestionFirstPhaseCommand" in source
    assert "RunKnowledgeExtractionWorkflowAfterUploadCommand" in source
    assert "workflow_runner = make_knowledge_extraction_workflow_after_upload" in source
    assert "await workflow_runner.execute(" in source
    assert "blocked_command_type" in source
    assert "drained_dispatched_count" in source
    assert "source_document_ref" in source
    assert "source_unit_count" in source
