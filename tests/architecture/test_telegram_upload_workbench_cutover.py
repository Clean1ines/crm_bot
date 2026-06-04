from __future__ import annotations

import importlib
from pathlib import Path


def test_platform_admin_telegram_upload_uses_workbench_composition() -> None:
    source = Path(
        "src/interfaces/telegram/platform_admin/knowledge_upload.py"
    ).read_text(encoding="utf-8")

    assert "upload_faq_workbench_knowledge_file" in source
    assert "QueueRepository" in source
    assert "require_faq_workbench_mode" in source
    assert "normalize_preprocessing_mode" not in source
    assert "src.domain.project_plane.knowledge_preprocessing" not in source

    forbidden = (
        "src.interfaces.composition.knowledge_upload",
        "upload_platform_admin_knowledge_file",
        "upload_knowledge_file",
        "process_knowledge_upload",
        "TASK_PROCESS_KNOWLEDGE_UPLOAD",
    )
    for marker in forbidden:
        assert marker not in source


def test_old_upload_composition_file_is_deleted() -> None:
    assert not Path("src/interfaces/composition/knowledge_upload.py").exists()


def test_upload_roots_import_without_old_upload_composition() -> None:
    for module in (
        "src.interfaces.http.knowledge",
        "src.interfaces.telegram.platform_admin.knowledge_upload",
        "src.interfaces.telegram.platform_bot",
        "src.interfaces.composition.faq_workbench_upload",
    ):
        importlib.import_module(module)
