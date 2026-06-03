from __future__ import annotations

import importlib
from pathlib import Path


def test_knowledge_upload_http_boundary_is_workbench_only() -> None:
    source = Path("src/interfaces/http/knowledge.py").read_text(encoding="utf-8")

    assert "src.interfaces.composition.faq_workbench_upload" in source
    assert "upload_faq_workbench_knowledge_file" in source
    assert "Only FAQ Workbench uploads are supported" in source

    forbidden = (
        "src.interfaces.composition.knowledge_upload",
        "upload_knowledge_file",
        "KnowledgeService(",
        "process_knowledge_upload",
        "TASK_PROCESS_KNOWLEDGE_UPLOAD",
    )
    for marker in forbidden:
        assert marker not in source


def test_non_faq_upload_modes_fail_closed_until_workbench_analog_exists() -> None:
    source = Path("src/interfaces/http/knowledge.py").read_text(encoding="utf-8")

    assert "mode != MODE_FAQ" in source
    assert "status_code=422" in source
    assert "first-class Workbench implementation" in source


def test_knowledge_http_module_imports_without_legacy_upload_path() -> None:
    module = importlib.import_module("src.interfaces.http.knowledge")

    assert module is not None
