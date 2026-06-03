from __future__ import annotations

import ast
from pathlib import Path

COMPOSITION = Path("src/interfaces/composition/faq_workbench_publish_ready.py")


def _imported_names_from_publish_ready_module(source: str) -> set[str]:
    tree = ast.parse(source)
    names: set[str] = set()

    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ImportFrom)
            and node.module == "src.application.workbench_commands.publish_ready"
        ):
            names.update(alias.asname or alias.name for alias in node.names)

    return names


def test_publish_ready_composition_uses_reconciled_fact_registry_service() -> None:
    source = COMPOSITION.read_text(encoding="utf-8")
    imported_names = _imported_names_from_publish_ready_module(source)

    assert "FaqWorkbenchPublishReadyService" in imported_names
    assert "PublishReadyCommand" in imported_names
    assert "PublishReadyRejectedError" in imported_names
    assert "service.publish_ready(" in source
    assert "published_snapshot_id" in source

    assert "WorkbenchPublishReadyCommand" not in imported_names
    assert "WorkbenchPublishReadyNotFoundError" not in imported_names
    assert "WorkbenchPublishReadyRejectedError" not in imported_names
    assert "publish_ready_document" not in source
    assert ".to_dict()" not in source


def test_publish_ready_composition_keeps_http_boundary_function_name() -> None:
    source = COMPOSITION.read_text(encoding="utf-8")

    assert "async def publish_workbench_ready_surfaces" in source
    assert '"publish_workbench_ready_surfaces"' in source
