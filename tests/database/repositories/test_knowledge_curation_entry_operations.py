from __future__ import annotations

import ast
from pathlib import Path


REPOSITORY_PATH = Path("src/infrastructure/db/repositories/knowledge_repository.py")
HELPER_PATH = Path(
    "src/infrastructure/db/repositories/knowledge_curation_entry_operations.py"
)


def _method_source(source: str, method_name: str, next_method_name: str) -> str:
    start = source.index(f"async def {method_name}(")
    end = source.index(f"async def {next_method_name}(", start)
    return source[start:end]


def test_curation_entry_operations_helper_owns_attach_and_rebuild_logic() -> None:
    helper_source = HELPER_PATH.read_text(encoding="utf-8")

    assert "async def attach_question_to_entry(" in helper_source
    assert "async def rebuild_entry_embedding(" in helper_source
    assert "UPDATE knowledge_entries" in helper_source
    assert "FROM knowledge_entry_source_refs" in helper_source
    assert "await update_retrieval_surface_metadata(" in helper_source
    assert "await upsert_retrieval_surface_from_payload(" in helper_source
    assert "await write_version_snapshot(" in helper_source
    assert "await usage_repo.record_event(" in helper_source


def test_repository_delegates_attach_and_rebuild_entry_operations() -> None:
    repository_source = REPOSITORY_PATH.read_text(encoding="utf-8")
    attach_source = _method_source(
        repository_source, "attach_question_to_entry", "rebuild_entry_embedding"
    )
    rebuild_source = _method_source(
        repository_source, "rebuild_entry_embedding", "delete_document_chunks"
    )

    assert "await run_attach_question_to_entry(" in attach_source
    assert "await run_rebuild_entry_embedding(" in rebuild_source

    for forbidden in (
        "UPDATE knowledge_entries",
        "FROM knowledge_entries",
        "FROM knowledge_entry_source_refs",
        "write_version_snapshot(",
        "embed_batch(",
        "update_retrieval_surface_metadata(",
        "upsert_retrieval_surface_from_payload(",
    ):
        assert forbidden not in attach_source
        assert forbidden not in rebuild_source


def test_repository_size_moves_below_family_extraction_threshold() -> None:
    repository_lines = len(REPOSITORY_PATH.read_text(encoding="utf-8").splitlines())
    assert repository_lines < 2500


def test_repository_methods_remain_parseable_after_family_extraction() -> None:
    tree = ast.parse(REPOSITORY_PATH.read_text(encoding="utf-8"))
    klass = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "KnowledgeRepository"
    )
    method_names = {
        node.name
        for node in klass.body
        if isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef)
    }

    assert "attach_question_to_entry" in method_names
    assert "rebuild_entry_embedding" in method_names
    assert "apply_manual_entry_merge" in method_names


def test_repository_delegates_status_content_restore_mutations() -> None:
    repository_source = REPOSITORY_PATH.read_text(encoding="utf-8")
    operations_source = HELPER_PATH.read_text(encoding="utf-8")

    assert "async def update_entry_status_visibility(" in operations_source
    assert "async def update_entry_content(" in operations_source
    assert "async def restore_entry_version(" in operations_source
    assert "UPDATE knowledge_entries" in operations_source
    assert "FROM knowledge_entry_versions" in operations_source
    assert "await update_retrieval_surface_content(" in operations_source
    assert "await delete_retrieval_surface(" in operations_source
    assert "await write_version_snapshot(" in operations_source
    assert "await mark_action_applied_raw(" in operations_source

    for method_name, next_method_name, delegate in (
        (
            "update_entry_status_visibility",
            "update_entry_content",
            "run_update_entry_status_visibility",
        ),
        (
            "update_entry_content",
            "apply_manual_entry_merge",
            "run_update_entry_content",
        ),
        (
            "restore_entry_version",
            "clear_project_knowledge",
            "run_restore_entry_version",
        ),
    ):
        method_source = _method_source(repository_source, method_name, next_method_name)
        assert delegate in method_source
        assert "UPDATE knowledge_entries" not in method_source
        assert "FROM knowledge_entry_versions" not in method_source
        assert "FROM knowledge_entry_source_refs" not in method_source


def test_repository_size_moves_below_second_family_extraction_threshold() -> None:
    repository_lines = len(REPOSITORY_PATH.read_text(encoding="utf-8").splitlines())
    assert repository_lines < 2250


def test_repository_delegates_manual_entry_merge_mutation() -> None:
    repository_source = REPOSITORY_PATH.read_text(encoding="utf-8")
    operations_source = HELPER_PATH.read_text(encoding="utf-8")

    assert "async def apply_manual_entry_merge(" in operations_source
    assert "idempotency_replay_missing_result" in operations_source
    assert "absorbed_already_merged" in operations_source
    assert "absorbed_version_conflict" in operations_source
    assert "source_refs_required_for_published_parent" in operations_source
    assert "await replace_entry_source_refs_from_payload(" in operations_source
    assert "await delete_retrieval_surface(" in operations_source
    assert "await write_version_snapshot(" in operations_source
    assert "await mark_action_in_progress_raw(" in operations_source

    source = _method_source(
        repository_source,
        "apply_manual_entry_merge",
        "create_manual_rebuild_embedding_action",
    )

    assert "await run_apply_manual_entry_merge(" in source
    assert "_merge_apply_result_from_payload(" in source
    assert "await mark_action_completed_with_result(" in source
    assert "UPDATE knowledge_entries" not in source
    assert "FROM knowledge_entries" not in source
    assert "replace_entry_source_refs_from_payload(" not in source
    assert "delete_retrieval_surface(" not in source
    assert "mark_action_in_progress_raw(" not in source


def test_repository_size_moves_below_manual_merge_extraction_threshold() -> None:
    repository_lines = len(REPOSITORY_PATH.read_text(encoding="utf-8").splitlines())
    assert repository_lines < 2000
