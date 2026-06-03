from __future__ import annotations

import inspect

import src.infrastructure.db.workbench_runtime_retrieval_repository as module
from src.infrastructure.db.workbench_runtime_retrieval_repository import (
    WorkbenchRuntimeRetrievalRepository,
)


def test_workbench_runtime_retrieval_repository_targets_published_runtime_entries() -> (
    None
):
    source = inspect.getsource(module)

    assert "knowledge_workbench_runtime_retrieval_entries" in source
    assert "status = 'published'" in source
    assert "visibility = 'runtime'" in source
    assert "knowledge_base" not in source


def test_workbench_runtime_retrieval_repository_implements_search_contract() -> None:
    assert hasattr(WorkbenchRuntimeRetrievalRepository, "search")
