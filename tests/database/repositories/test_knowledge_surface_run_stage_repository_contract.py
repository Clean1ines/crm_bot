from pathlib import Path


def test_repository_has_surface_run_and_stage_methods() -> None:
    source = Path("src/infrastructure/db/repositories/knowledge_repository.py").read_text(
        encoding="utf-8"
    )

    assert "async def create_surface_compiler_run(" in source
    assert "INSERT INTO knowledge_surface_compiler_runs" in source
    assert "async def update_surface_compiler_run_status(" in source
    assert "UPDATE knowledge_surface_compiler_runs" in source
    assert "async def create_surface_compiler_stage(" in source
    assert "INSERT INTO knowledge_surface_compiler_stages" in source


def test_repository_has_surface_run_and_stage_list_methods() -> None:
    source = Path("src/infrastructure/db/repositories/knowledge_repository.py").read_text(
        encoding="utf-8"
    )
    assert "async def get_latest_surface_run_for_document(" in source
    assert "async def list_surface_runs_for_document(" in source
    assert "FROM knowledge_surface_compiler_runs" in source
    assert "ORDER BY created_at DESC" in source
    assert "async def list_surface_stages_for_run(" in source
    assert "FROM knowledge_surface_compiler_stages" in source


def test_repository_has_surface_source_unit_persistence_methods() -> None:
    source = Path("src/infrastructure/db/repositories/knowledge_repository.py").read_text(encoding="utf-8")
    assert "async def save_surface_source_units(" in source
    assert "INSERT INTO knowledge_surface_source_units" in source
    assert "async def list_surface_source_units_for_run(" in source
    assert "FROM knowledge_surface_source_units" in source


def test_repository_has_surface_draft_persistence_methods() -> None:
    source = Path("src/infrastructure/db/repositories/knowledge_repository.py").read_text(encoding="utf-8")
    assert "async def save_surfaces(" in source
    assert "INSERT INTO knowledge_surfaces" in source
    assert "async def list_surfaces_for_run(" in source
    assert "FROM knowledge_surfaces" in source


def test_repository_has_surface_relation_persistence_methods() -> None:
    source = Path("src/infrastructure/db/repositories/knowledge_repository.py").read_text(encoding="utf-8")
    assert "async def save_surface_relations(" in source
    assert "INSERT INTO knowledge_surface_relations" in source
    assert "async def list_surface_relations_for_run(" in source
    assert "FROM knowledge_surface_relations" in source


def test_repository_has_surface_ownership_persistence_methods() -> None:
    source = Path("src/infrastructure/db/repositories/knowledge_repository.py").read_text(encoding="utf-8")
    assert "async def save_surface_question_ownership(" in source
    assert "INSERT INTO knowledge_surface_question_ownership" in source
    assert "async def list_surface_ownership_for_run(" in source
    assert "FROM knowledge_surface_question_ownership" in source


def test_repository_has_surface_reassignment_persistence_methods() -> None:
    source = Path("src/infrastructure/db/repositories/knowledge_repository.py").read_text(encoding="utf-8")
    assert "async def save_surface_question_reassignments(" in source
    assert "INSERT INTO knowledge_surface_question_reassignments" in source
    assert "async def list_surface_reassignments_for_run(" in source
    assert "FROM knowledge_surface_question_reassignments" in source


def test_repository_has_surface_merge_decision_persistence_methods() -> None:
    source = Path("src/infrastructure/db/repositories/knowledge_repository.py").read_text(encoding="utf-8")
    assert "async def save_surface_merge_decisions(" in source
    assert "INSERT INTO knowledge_surface_merge_decisions" in source
    assert "async def list_surface_merge_decisions_for_run(" in source
    assert "FROM knowledge_surface_merge_decisions" in source


def test_repository_has_document_level_surface_relation_and_ownership_methods() -> None:
    source = Path("src/infrastructure/db/repositories/knowledge_repository.py").read_text(encoding="utf-8")
    assert "async def list_surface_relations_for_document(" in source
    assert "async def list_surface_ownership_for_document(" in source
    assert "async def list_surface_reassignments_for_document(" in source
    assert "get_latest_surface_run_for_document(" in source
