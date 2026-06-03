from __future__ import annotations

import importlib
from pathlib import Path


def test_rag_eval_dataset_generator_uses_entry_kind_not_old_retrieval_surface() -> None:
    source = Path("src/application/rag_eval/dataset_generator.py").read_text(
        encoding="utf-8"
    )

    assert "src.domain.project_plane.knowledge_entry_kind" in source
    assert "RUNTIME_ENTRY_KIND_VALUES" in source
    assert "knowledge_retrieval_surface" not in source
    assert "knowledge_compilation" not in source


def test_rag_eval_dataset_generator_imports_without_legacy_surface_domain() -> None:
    module = importlib.import_module("src.application.rag_eval.dataset_generator")

    assert module is not None
