from __future__ import annotations

import importlib
from pathlib import Path


def test_workbench_upload_api_contract_has_no_legacy_patch_points() -> None:
    module = importlib.import_module("src.interfaces.http.knowledge")
    source = Path("src/interfaces/http/knowledge.py").read_text(encoding="utf-8")

    assert not hasattr(module, "ChunkerService")
    assert not hasattr(module, "jwt")
    assert "src.interfaces.composition.knowledge_upload" not in source
    assert "process_knowledge_upload" not in source


def test_workbench_upload_api_contract_has_transferred_donor_semantics() -> None:
    source = Path("src/interfaces/http/knowledge.py").read_text(encoding="utf-8")

    required = (
        "get_current_user_id",
        "user_has_project_role",
        "is_platform_admin",
        "Unsupported file type",
        "UPLOAD_TOO_LARGE_DETAIL",
        "Could not read file",
        "RunSourceIngestionFirstPhaseCommand",
        "RunKnowledgeExtractionWorkflowAfterUploadCommand",
        "make_knowledge_extraction_workflow_after_upload",
    )
    for marker in required:
        assert marker in source
