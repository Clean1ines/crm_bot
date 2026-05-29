from __future__ import annotations

import pytest

from src.domain.project_plane.knowledge_artifact_cleanup import (
    MODE_CLEAR_PROJECT,
    MODE_DELETE_DOCUMENT,
    MODE_MANUAL_CANCEL,
    MODE_RESET_FOR_REPROCESS,
    SCOPE_DOCUMENT,
    SCOPE_PROJECT,
    build_document_delete_cleanup_plan,
    build_document_reset_cleanup_plan,
    build_manual_cancel_cleanup_plan,
    build_project_clear_cleanup_plan,
)


def test_manual_cancel_is_not_destructive_cleanup() -> None:
    plan = build_manual_cancel_cleanup_plan(
        project_id="project-1",
        document_id="document-1",
    )

    assert plan.scope == SCOPE_DOCUMENT
    assert plan.mode == MODE_MANUAL_CANCEL
    assert plan.destructive is False
    assert plan.cancel_running_jobs is True
    assert plan.cleanup_execution_queue is True
    assert plan.delete_document_row is False
    assert plan.reset_document_state is False
    assert plan.cleanup_source_chunks is False
    assert plan.cleanup_entries is False
    assert "knowledge_documents" in plan.affected_tables
    assert "execution_queue" in plan.affected_tables


def test_document_reset_for_reprocess_is_destructive_cleanup() -> None:
    plan = build_document_reset_cleanup_plan(
        project_id="project-1",
        document_id="document-1",
    )

    assert plan.scope == SCOPE_DOCUMENT
    assert plan.mode == MODE_RESET_FOR_REPROCESS
    assert plan.destructive is True
    assert plan.reset_document_state is True
    assert plan.delete_document_row is False
    assert plan.cleanup_source_chunks is True
    assert plan.cleanup_entries is True
    assert plan.cleanup_retrieval_surface is True
    assert plan.cleanup_compiler_artifacts is True
    assert plan.cleanup_surface_artifacts is True
    assert plan.cleanup_rag_eval_artifacts is True
    assert plan.cleanup_execution_queue is True
    assert "knowledge_source_chunks" in plan.affected_tables
    assert "knowledge_surface_compiler_runs" in plan.affected_tables
    assert "rag_eval_runs" in plan.affected_tables


def test_delete_document_is_destructive_cleanup() -> None:
    plan = build_document_delete_cleanup_plan(
        project_id="project-1",
        document_id="document-1",
    )

    assert plan.scope == SCOPE_DOCUMENT
    assert plan.mode == MODE_DELETE_DOCUMENT
    assert plan.destructive is True
    assert plan.delete_document_row is True
    assert plan.reset_document_state is False
    assert plan.cleanup_source_chunks is True
    assert plan.cleanup_entries is True
    assert plan.cleanup_execution_queue is True
    assert "knowledge_documents" in plan.affected_tables
    assert "knowledge_entries" in plan.affected_tables
    assert "execution_queue" in plan.affected_tables


def test_clear_project_is_destructive_cleanup() -> None:
    plan = build_project_clear_cleanup_plan(project_id="project-1")

    assert plan.scope == SCOPE_PROJECT
    assert plan.mode == MODE_CLEAR_PROJECT
    assert plan.document_id is None
    assert plan.destructive is True
    assert plan.clear_project_documents is True
    assert plan.cleanup_source_chunks is True
    assert plan.cleanup_entries is True
    assert plan.cleanup_surface_artifacts is True
    assert plan.cleanup_execution_queue is True
    assert "knowledge_documents" in plan.affected_tables
    assert "knowledge_surfaces" in plan.affected_tables
    assert "knowledge_surface_source_units" in plan.affected_tables
    assert "execution_queue" in plan.affected_tables


def test_document_scope_requires_document_id() -> None:
    with pytest.raises(ValueError, match="document_id"):
        build_document_reset_cleanup_plan(project_id="project-1", document_id="")
