from __future__ import annotations

import ast
import importlib
from pathlib import Path


DELETED_FILES = (
    "src/infrastructure/db/repositories/knowledge_answer_candidate_persistence.py",
    "src/infrastructure/db/repositories/knowledge_answer_candidate_queries.py",
    "src/infrastructure/db/repositories/knowledge_compiler_run_persistence.py",
    "src/infrastructure/db/repositories/knowledge_compiler_payloads.py",
    "src/infrastructure/db/repositories/knowledge_entry_persistence.py",
    "src/infrastructure/db/repositories/knowledge_source_chunk_persistence.py",
    "src/infrastructure/db/repositories/knowledge_curation_entry_operations.py",
    "src/infrastructure/db/repositories/knowledge_curation_action_persistence.py",
    "src/infrastructure/db/repositories/knowledge_curation_mappers.py",
    "src/domain/project_plane/knowledge_retrieval_surface.py",
    "src/domain/project_plane/knowledge_curation.py",
    "src/domain/project_plane/embedding_text.py",
    "src/application/services/knowledge_curation_service.py",
)

FORBIDDEN_REPOSITORY_MARKERS = (
    "_RetiredLegacyRepositorySymbol",
    "knowledge_answer_candidate_persistence",
    "knowledge_answer_candidate_queries",
    "knowledge_compiler_run_persistence",
    "knowledge_compiler_payloads",
    "knowledge_entry_persistence",
    "knowledge_source_chunk_persistence",
    "knowledge_curation_entry_operations",
    "knowledge_curation_action_persistence",
    "knowledge_curation_mappers",
    "knowledge_retrieval_surface",
    "knowledge_curation",
    "knowledge_compilation",
    "CANONICAL_EMBEDDING_TEXT_VERSION",
    "KnowledgeAnswerCandidateSummaryView",
    "KnowledgeCompilerBatchView",
    "CanonicalKnowledgeEntry",
    "AnswerCandidate",
    "CandidateCluster",
    "CompilerRun",
    "CompilerBatch",
    "KnowledgeEntryStatus",
    "KnowledgeEntryVisibility",
    "SourceChunk",
)


def test_legacy_repository_zoo_files_are_deleted() -> None:
    for path in DELETED_FILES:
        assert not Path(path).exists(), f"{path} must stay deleted"


def test_knowledge_repository_no_longer_contains_quarantine_or_legacy_zoo() -> None:
    source = Path(
        "src/infrastructure/db/repositories/knowledge_repository.py"
    ).read_text(encoding="utf-8")

    for marker in FORBIDDEN_REPOSITORY_MARKERS:
        assert marker not in source, f"knowledge_repository.py still contains {marker}"


def test_knowledge_repository_imports_without_legacy_zoo() -> None:
    module = importlib.import_module(
        "src.infrastructure.db.repositories.knowledge_repository"
    )

    assert hasattr(module, "KnowledgeRepository")


def test_knowledge_repository_has_no_imports_from_deleted_modules() -> None:
    source = Path(
        "src/infrastructure/db/repositories/knowledge_repository.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)

    deleted_modules = {
        "src." + path[:-3].replace("/", ".")
        for path in DELETED_FILES
        if path.endswith(".py")
    }

    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            assert node.module not in deleted_modules


def test_knowledge_repository_no_longer_contains_old_edit_action_methods() -> None:
    source = Path(
        "src/infrastructure/db/repositories/knowledge_repository.py"
    ).read_text(encoding="utf-8")

    forbidden = (
        "create_or_get_knowledge_edit_action",
        "mark_knowledge_edit_action_applied",
        "mark_knowledge_edit_action_rejected",
        "mark_knowledge_edit_action_failed",
        "attach_question_to_entry",
        "rebuild_entry_embedding",
        "create_or_get_result_action",
        "mark_action_applied",
        "mark_action_rejected",
        "mark_action_failed",
        "run_attach_question_to_entry",
        "run_rebuild_entry_embedding",
    )

    for marker in forbidden:
        assert marker not in source, f"knowledge_repository.py still contains {marker}"
