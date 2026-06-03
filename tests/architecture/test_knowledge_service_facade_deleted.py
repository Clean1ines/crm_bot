from __future__ import annotations

import importlib
from pathlib import Path


def test_retired_knowledge_service_facade_file_is_deleted() -> None:
    assert not Path("src/application/services/knowledge_service.py").exists()


def test_production_code_does_not_import_retired_knowledge_service_facade() -> None:
    forbidden = (
        "from src.application.services.knowledge_service import",
        "src.application.services.knowledge_service",
        "KnowledgeService(",
    )

    for path in Path("src").rglob("*.py"):
        source = path.read_text(encoding="utf-8", errors="replace")
        for marker in forbidden:
            assert marker not in source, f"{path} still contains {marker}"


def test_workbench_and_commercial_replacements_import_without_facade() -> None:
    modules = (
        "src.interfaces.http.knowledge",
        "src.interfaces.composition.faq_workbench_upload",
        "src.interfaces.composition.faq_workbench_clear",
        "src.interfaces.composition.faq_workbench_delete",
        "src.interfaces.composition.faq_workbench_resume",
        "src.application.services.commercial_truth_review_service",
        "src.infrastructure.db.repositories.commercial_price_repository",
        "src.infrastructure.db.repositories.model_usage_repository",
    )

    for module in modules:
        importlib.import_module(module)


def test_old_facade_tests_are_deleted() -> None:
    assert not Path(
        "tests/application/services/test_knowledge_service_delete_document.py"
    ).exists()
    assert not Path(
        "tests/application/services/test_knowledge_service_project_commercial_truth_review.py"
    ).exists()
