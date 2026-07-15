from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import asyncpg
import pytest

from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval import (
    WorkbenchRagEvalCurrentPhase,
    WorkbenchRagEvalRun,
    WorkbenchRagEvalRunProgress,
    WorkbenchRagEvalRunStatus,
)
from src.contexts.knowledge_workbench.rag_eval.infrastructure.postgres.postgres_workbench_rag_eval_repository import (
    PostgresWorkbenchRagEvalRepository,
)


REPO_ROOT = Path(__file__).resolve().parents[6]
MIGRATIONS_DIR = REPO_ROOT / "migrations"
REQUIRED_RAG_EVAL_RUN_COLUMNS = {
    "run_id",
    "project_id",
    "publication_id",
    "source_document_ref",
    "status",
    "question_generation_model",
    "question_generation_prompt_version",
    "total_entries",
    "total_questions",
    "completed_questions",
    "top1_hits",
    "top3_hits",
    "top5_hits",
    "misses",
    "created_at",
    "started_at",
    "completed_at",
    "error_message",
    "current_phase",
    "blocked_reason",
    "failed_reason",
    "updated_at",
    "selected_entries",
    "scheduled_generation_items",
    "waiting_work_items",
    "running_work_items",
    "completed_work_items",
    "failed_work_items",
    "generated_question_sets",
    "capacity_next_due_at",
    "capacity_model_ref",
    "capacity_account_ref",
    "retrieval_total_questions",
    "retrieval_evaluated_questions",
    "retrieval_pass_strong",
    "retrieval_pass_weak",
    "retrieval_confusions",
    "retrieval_misses",
    "retrieval_existing_alias_failures",
    "adjudication_total",
    "adjudication_waiting",
    "adjudication_running",
    "adjudication_completed",
    "adjudication_failed",
    "promotion_candidate_count",
}


def _database_url_with_database(database_url: str, database_name: str) -> str:
    parts = urlsplit(database_url)
    return urlunsplit(parts._replace(path=f"/{database_name}"))


async def _apply_canonical_migration_chain(database_url: str) -> None:
    conn = await asyncpg.connect(database_url)
    try:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS public.schema_migrations (
                id SERIAL PRIMARY KEY,
                filename TEXT NOT NULL UNIQUE,
                applied_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
            """
        )
        applied = {
            row["filename"]
            for row in await conn.fetch("SELECT filename FROM public.schema_migrations")
        }
        for migration_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if migration_file.name in applied:
                continue
            await conn.execute(migration_file.read_text(encoding="utf-8"))
            await conn.execute(
                "INSERT INTO public.schema_migrations (filename) VALUES ($1)",
                migration_file.name,
            )
    finally:
        await conn.close()


async def _drop_database(database_url: str, database_name: str) -> None:
    maintenance_url = _database_url_with_database(database_url, "postgres")
    conn = await asyncpg.connect(maintenance_url)
    try:
        await conn.execute(
            """
            SELECT pg_terminate_backend(pid)
            FROM pg_stat_activity
            WHERE datname = $1
              AND pid <> pg_backend_pid()
            """,
            database_name,
        )
        await conn.execute(f'DROP DATABASE IF EXISTS "{database_name}"')
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_migrated_postgres_supports_rag_eval_create_and_latest_round_trip() -> (
    None
):
    base_database_url = os.getenv("DATABASE_URL")
    if not base_database_url:
        pytest.skip("DATABASE_URL is required for migration round-trip test")

    database_name = f"tmp_rag_eval_round_trip_{uuid.uuid4().hex}"
    maintenance_url = _database_url_with_database(base_database_url, "postgres")
    conn = await asyncpg.connect(maintenance_url)
    try:
        await conn.execute(f'CREATE DATABASE "{database_name}"')
    except asyncpg.PostgresError as exc:
        pytest.skip(f"test database user cannot create temporary databases: {exc}")
    finally:
        await conn.close()

    temp_database_url = _database_url_with_database(base_database_url, database_name)
    try:
        await _apply_canonical_migration_chain(temp_database_url)

        pool = await asyncpg.create_pool(temp_database_url, min_size=1, max_size=2)
        try:
            columns = {
                row["column_name"]
                for row in await pool.fetch(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'knowledge_workbench_rag_eval_runs'
                    """
                )
            }
            assert REQUIRED_RAG_EVAL_RUN_COLUMNS <= columns

            repository = PostgresWorkbenchRagEvalRepository(pool)
            created_at = datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)
            capacity_next_due_at = created_at + timedelta(minutes=5)
            project_id = str(uuid.uuid4())

            await repository.create_run(
                run=WorkbenchRagEvalRun(
                    run_id="run-postgres-round-trip",
                    project_id=project_id,
                    publication_id=None,
                    source_document_ref=None,
                    status=WorkbenchRagEvalRunStatus.WAITING_CAPACITY,
                    question_generation_model="qwen/qwen3-32b",
                    question_generation_prompt_version="rag-eval-v2",
                    total_entries=4,
                    total_questions=0,
                    completed_questions=0,
                    top1_hits=0,
                    top3_hits=0,
                    top5_hits=0,
                    misses=0,
                    created_at=created_at,
                    started_at=created_at,
                    completed_at=None,
                    error_message=None,
                    current_phase=WorkbenchRagEvalCurrentPhase.QUESTION_GENERATION,
                    blocked_reason="provider_capacity_wait",
                    failed_reason=None,
                    updated_at=created_at,
                    progress=WorkbenchRagEvalRunProgress(
                        selected_entries=4,
                        scheduled_generation_items=4,
                        waiting=2,
                        running=1,
                        completed=1,
                        failed=0,
                        generated_question_sets=1,
                        adjudication_total=3,
                        adjudication_waiting=1,
                        adjudication_running=1,
                        adjudication_completed=1,
                        adjudication_failed=0,
                        promotion_candidate_count=2,
                    ),
                    capacity_next_due_at=capacity_next_due_at,
                    capacity_model_ref="qwen/qwen3-32b",
                    capacity_account_ref="groq_org_primary",
                )
            )

            latest = await repository.get_latest_run(project_id=project_id)

            assert latest is not None
            assert latest.run_id == "run-postgres-round-trip"
            assert latest.project_id == project_id
            assert latest.status is WorkbenchRagEvalRunStatus.WAITING_CAPACITY
            assert (
                latest.current_phase is WorkbenchRagEvalCurrentPhase.QUESTION_GENERATION
            )
            assert latest.blocked_reason == "provider_capacity_wait"
            assert latest.failed_reason is None
            assert latest.progress.selected_entries == 4
            assert latest.progress.scheduled_generation_items == 4
            assert latest.progress.waiting == 2
            assert latest.progress.running == 1
            assert latest.progress.completed == 1
            assert latest.progress.failed == 0
            assert latest.progress.generated_question_sets == 1
            assert latest.capacity_next_due_at == capacity_next_due_at
            assert latest.capacity_model_ref == "qwen/qwen3-32b"
            assert latest.capacity_account_ref == "groq_org_primary"
            assert latest.progress.adjudication_total == 3
            assert latest.progress.adjudication_waiting == 1
            assert latest.progress.adjudication_running == 1
            assert latest.progress.adjudication_completed == 1
            assert latest.progress.adjudication_failed == 0
            assert latest.progress.promotion_candidate_count == 2
            assert latest.promotion_candidate_count == 2
        finally:
            await pool.close()
    finally:
        await _drop_database(base_database_url, database_name)
