from __future__ import annotations

import importlib
from pathlib import Path


def test_search_ranking_does_not_import_old_retrieval_surface() -> None:
    source = Path(
        "src/infrastructure/db/repositories/knowledge_search_ranking.py"
    ).read_text(encoding="utf-8")

    assert "knowledge_retrieval_surface" not in source
    assert "knowledge_compilation" not in source
    assert "RUNTIME_ENTRY_KIND_VALUES" in source


def test_search_ranking_imports_without_legacy_compiler_domain() -> None:
    module = importlib.import_module(
        "src.infrastructure.db.repositories.knowledge_search_ranking"
    )

    assert hasattr(module, "search_score_and_trace")
    assert hasattr(module, "preview_score_and_trace")
