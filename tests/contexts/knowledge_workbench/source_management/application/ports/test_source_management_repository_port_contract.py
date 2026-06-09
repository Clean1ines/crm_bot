from __future__ import annotations

from src.contexts.knowledge_workbench.source_management.application.ports.source_management_repository_port import SourceManagementRepositoryPort


def test_source_management_repository_port_exposes_expected_methods() -> None:
    assert hasattr(SourceManagementRepositoryPort, "save_source_document")
    assert hasattr(SourceManagementRepositoryPort, "load_source_document")
    assert hasattr(SourceManagementRepositoryPort, "save_source_units")
    assert hasattr(SourceManagementRepositoryPort, "list_source_units_for_document")
    assert hasattr(SourceManagementRepositoryPort, "load_source_unit")
