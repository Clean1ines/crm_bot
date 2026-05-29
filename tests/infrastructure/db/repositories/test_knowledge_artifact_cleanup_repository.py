from __future__ import annotations

from uuid import uuid4

import pytest

from src.domain.project_plane.knowledge_artifact_cleanup import (
    build_document_reset_cleanup_plan,
    build_manual_cancel_cleanup_plan,
    build_project_clear_cleanup_plan,
)
from src.infrastructure.db.repositories.knowledge_artifact_cleanup import (
    TERMINAL_QUEUE_STATUSES,
    cleanup_document_artifacts,
    cleanup_project_artifacts,
)
from src.infrastructure.db.repositories.knowledge_repository import KnowledgeRepository


class RecordingTransaction:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object | None,
    ) -> bool:
        return False


class RecordingConnection:
    def __init__(self) -> None:
        self.execute_calls: list[tuple[str, tuple[object, ...]]] = []

    async def execute(self, query: str, *args: object) -> str:
        self.execute_calls.append((query, args))
        keyword = query.strip().split(maxsplit=1)[0].upper()
        return f"{keyword} 1"

    def transaction(self) -> RecordingTransaction:
        return RecordingTransaction()


class RecordingAcquire:
    def __init__(self, conn: RecordingConnection) -> None:
        self._conn = conn

    async def __aenter__(self) -> RecordingConnection:
        return self._conn

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object | None,
    ) -> bool:
        return False


class RecordingPool:
    def __init__(self, conn: RecordingConnection) -> None:
        self._conn = conn

    def acquire(self) -> RecordingAcquire:
        return RecordingAcquire(self._conn)


def _sql(conn: RecordingConnection) -> str:
    return "\\n".join(query for query, _args in conn.execute_calls)


def _args_repr(conn: RecordingConnection) -> str:
    return repr([args for _query, args in conn.execute_calls])


@pytest.mark.asyncio
async def test_cleanup_one_document_removes_all_document_artifacts() -> None:
    project_id = str(uuid4())
    document_id = str(uuid4())
    conn = RecordingConnection()
    repo = KnowledgeRepository(RecordingPool(conn))

    result = await repo.cleanup_document_artifacts(
        build_document_reset_cleanup_plan(
            project_id=project_id,
            document_id=document_id,
        )
    )

    executed_sql = _sql(conn)

    assert result.destructive is True
    assert result.affected_total > 0
    queue_update_args = next(
        args for query, args in conn.execute_calls if "UPDATE execution_queue" in query
    )

    assert "UPDATE execution_queue" in executed_sql
    assert "payload::jsonb ->> 'document_id' = $1" in executed_sql
    assert "NOT (status = ANY($3::text[]))" in executed_sql
    assert queue_update_args[2] == list(TERMINAL_QUEUE_STATUSES)

    for table_name in (
        "knowledge_retrieval_surface",
        "knowledge_entry_source_refs",
        "knowledge_entry_versions",
        "knowledge_edit_actions",
        "knowledge_entries",
        "knowledge_compiler_batches",
        "knowledge_compilation_metrics",
        "knowledge_candidate_cluster_members",
        "knowledge_answer_candidates",
        "knowledge_candidate_clusters",
        "knowledge_compiler_runs",
        "knowledge_source_chunks",
        "knowledge_surface_compiler_runs",
        "knowledge_surface_compiler_stages",
        "knowledge_surface_source_units",
        "knowledge_surfaces",
        "knowledge_surface_relations",
        "knowledge_surface_question_ownership",
        "knowledge_surface_question_reassignments",
        "knowledge_surface_merge_decisions",
        "knowledge_surface_candidates",
        "knowledge_surface_answer_drafts",
        "knowledge_surface_local_relations",
        "knowledge_surface_global_relations",
        "knowledge_surface_rejected_questions",
        "knowledge_surface_reconciliation_runs",
        "rag_eval_review_groups",
        "rag_eval_question_reviews",
        "rag_eval_results",
        "rag_eval_runs",
        "rag_eval_questions",
        "rag_eval_datasets",
        "knowledge_base",
    ):
        assert table_name in executed_sql

    assert "UPDATE knowledge_documents" in executed_sql
    assert "DELETE FROM knowledge_documents" not in executed_sql


@pytest.mark.asyncio
async def test_cleanup_project_removes_all_project_knowledge_artifacts() -> None:
    project_id = str(uuid4())
    conn = RecordingConnection()
    repo = KnowledgeRepository(RecordingPool(conn))

    result = await repo.cleanup_project_artifacts(
        build_project_clear_cleanup_plan(project_id=project_id)
    )

    executed_sql = _sql(conn)

    assert result.destructive is True
    assert result.affected_total > 0
    assert "UPDATE execution_queue" in executed_sql
    assert "payload::jsonb ->> 'project_id' = $1" in executed_sql
    assert "DELETE FROM knowledge_documents" in executed_sql
    assert "WHERE project_id = $1" in executed_sql

    for table_name in (
        "knowledge_retrieval_surface",
        "knowledge_entry_source_refs",
        "knowledge_entries",
        "knowledge_compiler_batches",
        "knowledge_compiler_runs",
        "knowledge_answer_candidates",
        "knowledge_candidate_clusters",
        "knowledge_source_chunks",
        "knowledge_surface_compiler_runs",
        "knowledge_surface_source_units",
        "knowledge_surfaces",
        "knowledge_surface_question_ownership",
        "knowledge_surface_question_reassignments",
        "knowledge_surface_merge_decisions",
        "rag_eval_runs",
        "rag_eval_datasets",
        "knowledge_edit_actions",
        "knowledge_entry_versions",
        "knowledge_base",
    ):
        assert table_name in executed_sql


@pytest.mark.asyncio
async def test_manual_cancel_plan_does_not_cleanup_and_preserves_checkpoints() -> None:
    project_id = str(uuid4())
    document_id = str(uuid4())
    conn = RecordingConnection()

    result = await cleanup_document_artifacts(
        conn,
        project_id=project_id,
        document_id=document_id,
        plan=build_manual_cancel_cleanup_plan(
            project_id=project_id,
            document_id=document_id,
        ),
    )

    assert result.destructive is False
    assert result.affected_total == 0
    assert result.warnings
    assert conn.execute_calls == []


@pytest.mark.asyncio
async def test_cleanup_does_not_touch_project_settings_bot_config_or_users() -> None:
    project_id = str(uuid4())
    conn = RecordingConnection()

    await cleanup_project_artifacts(
        conn,
        project_id=project_id,
        plan=build_project_clear_cleanup_plan(project_id=project_id),
    )

    executed_sql = _sql(conn).lower()

    forbidden_fragments = (
        "delete from projects",
        "update projects",
        "delete from project_members",
        "update project_members",
        "delete from users",
        "update users",
        "delete from bot_tokens",
        "update bot_tokens",
        "delete from project_channels",
        "update project_channels",
        "delete from project_settings",
        "update project_settings",
    )

    for fragment in forbidden_fragments:
        assert fragment not in executed_sql
