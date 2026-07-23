from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import urlsplit, urlunsplit

import asyncpg
import pytest

from src.contexts.capacity_runtime.domain.capacity_policy import CapacityAdmissionPolicy
from src.contexts.execution_runtime.application.use_cases.ensure_work_items_scheduled import (
    EnsureWorkItemsScheduled,
    EnsureWorkItemsScheduledCommand,
)
from src.contexts.execution_runtime.domain.value_objects.worker_ref import WorkerRef
from src.contexts.execution_runtime.infrastructure.postgres.postgres_work_item_scheduling_repository import (
    PostgresWorkItemSchedulingRepository,
)
from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval import (
    WorkbenchRagEvalCurrentPhase,
    WorkbenchRagEvalQuestion,
    WorkbenchRagEvalQuestionAmbiguityRisk,
    WorkbenchRagEvalQuestionKind,
    WorkbenchRagEvalQuestionRole,
    WorkbenchRagEvalQuestionSource,
    WorkbenchRagEvalQuestionStatus,
    WorkbenchRagEvalRun,
    WorkbenchRagEvalRunProgress,
    WorkbenchRagEvalRunStatus,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.plan_workbench_rag_eval_question_generation_work import (
    WorkbenchRagEvalQuestionGenerationWorkPlanner,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.drain_workbench_rag_eval_workflow_commands import (
    WorkbenchRagEvalWorkflowCommandHandlerFailed,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.workbench_rag_eval_dispatch_preparation import (
    make_question_generation_dispatch_preparation_builder,
    workbench_rag_eval_route_catalog,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.workbench_rag_eval_workflow_definition import (
    WorkbenchRagEvalWorkflowCommandType,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.workbench_rag_eval_work_kinds import (
    WORKBENCH_RAG_EVAL_QUESTION_GENERATION_WORK_KIND,
)
from src.contexts.knowledge_workbench.rag_eval.infrastructure.postgres.postgres_workbench_rag_eval_repository import (
    PostgresWorkbenchRagEvalRepository,
)
from src.contexts.knowledge_workbench.observability.application.models.frontend_workflow_event_cursor import (
    FrontendWorkflowEventCursor,
)
from src.contexts.knowledge_workbench.observability.application.projectors.project_frontend_workflow_event import (
    ProjectFrontendWorkflowEvent,
)
from src.contexts.knowledge_workbench.observability.application.projectors.workbench_rag_eval_frontend_workflow_event_projector import (
    WorkbenchRagEvalFrontendWorkflowEventProjector,
)
from src.contexts.knowledge_workbench.observability.infrastructure.postgres.postgres_frontend_workflow_event_repository import (
    PostgresFrontendWorkflowEventRepository,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.handle_reconcile_workbench_rag_eval_question_generation_progress_command import (
    HandleReconcileWorkbenchRagEvalQuestionGenerationProgressCommand,
    HandleReconcileWorkbenchRagEvalQuestionGenerationProgressCommandHandler,
)
from src.contexts.knowledge_workbench.retrieval.application.models.published_workbench_retrieval import (
    PublishedWorkbenchRetrievalResult,
    PublishedWorkbenchRetrievalSourceRef,
)
from src.contexts.execution_runtime.application.ports.work_item_progress_read_repository_port import (
    WorkItemProgressSummary,
)
from src.contexts.llm_runtime.application.capacity.project_llm_capacity_to_capacity_runtime import (
    ProjectLlmCapacityToCapacityRuntime,
)
from src.contexts.llm_runtime.application.capacity.select_active_llm_model_capacity import (
    SelectActiveLlmModelCapacity,
)
from src.contexts.llm_runtime.application.ports.llm_dispatch_executor_port import (
    LlmDispatchExecutionInput,
    LlmDispatchExecutionStatus,
)
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_chat_request_builder import (
    JsonValue,
)
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_dispatch_executor import (
    GroqDispatchExecutor,
)
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_model_catalog_seed import (
    build_groq_free_plan_model_profiles,
    model_budget_profile_for_ref,
)
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_transport_port import (
    GroqTransportResponse,
)
from src.interfaces.composition.prepare_llm_dispatch_batch import (
    DispatchPreparationBuilderRegistry,
    PrepareLlmDispatchBatch,
    PrepareLlmDispatchBatchCommand,
)
from src.contexts.workflow_runtime.domain.entities.workflow_command import (
    WorkflowCommand,
    WorkflowCommandStatus,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_command_id import (
    WorkflowCommandId,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_idempotency_key import (
    WorkflowIdempotencyKey,
)
from src.contexts.workflow_runtime.infrastructure.postgres.postgres_command_log_repository import (
    PostgresCommandLogRepository,
)
from src.contexts.workflow_runtime.infrastructure.postgres.postgres_workflow_runtime_unit_of_work import (
    PostgresWorkflowRuntimeUnitOfWork,
)
from src.interfaces.composition import (
    workbench_rag_eval_workflow_runtime as runtime_module,
)
from src.interfaces.composition.workbench_rag_eval_workflow_runtime import (
    WorkbenchRagEvalWorkflowRuntimeComposition,
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
RAG_EVAL_V2_GENERATED_QUESTION_KINDS = (
    WorkbenchRagEvalQuestionKind.DIRECT_PARAPHRASE,
    WorkbenchRagEvalQuestionKind.LEXICAL_VARIANT,
    WorkbenchRagEvalQuestionKind.NAIVE_USER,
    WorkbenchRagEvalQuestionKind.ENTITY_FIRST,
    WorkbenchRagEvalQuestionKind.ACTION_FIRST,
    WorkbenchRagEvalQuestionKind.CONSTRAINT_FIRST,
    WorkbenchRagEvalQuestionKind.DOMAIN_SPECIFIC,
)


class FakeGroqTransport:
    def __init__(self) -> None:
        self.payloads: list[dict[str, JsonValue]] = []

    def post_chat_completions(
        self,
        *,
        payload: dict[str, JsonValue],
    ) -> GroqTransportResponse:
        self.payloads.append(payload)
        return GroqTransportResponse(
            status_code=200,
            headers={},
            body={
                "choices": [{"message": {"content": '{"ok": true}'}}],
                "usage": {"prompt_tokens": 7, "completion_tokens": 11},
            },
        )


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


def _rag_eval_entry(*, project_id: str) -> PublishedWorkbenchRetrievalResult:
    return PublishedWorkbenchRetrievalResult(
        runtime_entry_id="runtime-entry-1",
        publication_id="publication-1",
        project_id=project_id,
        source_document_ref=None,
        fact_id="fact-1",
        curation_item_ref=None,
        claim="Claim one",
        possible_questions=("Question one?",),
        exclusion_scope=None,
        evidence_block="Evidence one",
        source_claim_refs=("claim-1",),
        embedding_text="Embedding text one",
        score=1.0,
        rank=1,
        source_ref=PublishedWorkbenchRetrievalSourceRef(
            workflow_run_id=None,
            source_document_ref=None,
            curation_item_ref=None,
            source_claim_refs=("claim-1",),
        ),
    )


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
                    question_generation_model="qwen/qwen3.6-27b",
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
                    capacity_model_ref="qwen/qwen3.6-27b",
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
            assert latest.capacity_model_ref == "qwen/qwen3.6-27b"
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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("question_counts_by_entry", "expected_complete"),
    [
        pytest.param((), False, id="zero-generated-questions"),
        pytest.param((10,), True, id="complete-set"),
        pytest.param((9,), False, id="incomplete-set"),
        pytest.param((10, 10, 7), False, id="multiple-entries-with-sum"),
    ],
)
async def test_has_complete_question_sets_uses_integer_sql_boundary(
    question_counts_by_entry: tuple[int, ...],
    expected_complete: bool,
) -> None:
    base_database_url = os.getenv("DATABASE_URL")
    if not base_database_url:
        pytest.skip("DATABASE_URL is required for question coverage test")

    database_name = f"tmp_rag_eval_question_coverage_{uuid.uuid4().hex}"
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
            repository = PostgresWorkbenchRagEvalRepository(pool)
            project_id = str(uuid.uuid4())
            run_id = f"run-question-coverage-{uuid.uuid4().hex}"
            created_at = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)
            await repository.create_run(
                run=WorkbenchRagEvalRun(
                    run_id=run_id,
                    project_id=project_id,
                    publication_id=None,
                    source_document_ref=None,
                    status=WorkbenchRagEvalRunStatus.RUNNING,
                    question_generation_model="qwen/qwen3.6-27b",
                    question_generation_prompt_version="rag-eval-v2",
                    total_entries=len(question_counts_by_entry),
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
                    updated_at=created_at,
                )
            )
            questions: list[WorkbenchRagEvalQuestion] = []
            for entry_index, question_count in enumerate(
                question_counts_by_entry,
                start=1,
            ):
                entry_ref = f"runtime-entry-{entry_index}"
                for question_index in range(question_count):
                    questions.append(
                        WorkbenchRagEvalQuestion(
                            question_id=(
                                f"question:{run_id}:{entry_ref}:{question_index}"
                            ),
                            run_id=run_id,
                            project_id=project_id,
                            expected_runtime_entry_id=entry_ref,
                            expected_fact_id=f"fact-{entry_index}",
                            question=f"Question {entry_index}-{question_index}?",
                            question_kind=WorkbenchRagEvalQuestionKind.PARAPHRASE,
                            source=WorkbenchRagEvalQuestionSource.GENERATED,
                            generation_model="qwen/qwen3.6-27b",
                            prompt_version="rag-eval-v2",
                            contract_version="workbench_rag_eval_questions.v2",
                            promotion_eligible=True,
                            ambiguity_risk=WorkbenchRagEvalQuestionAmbiguityRisk.LOW,
                            generation_rationale="coverage regression",
                            generation_account_ref=None,
                            generation_slot_index=None,
                            status=WorkbenchRagEvalQuestionStatus.CREATED,
                            created_at=created_at,
                            evaluation_role=WorkbenchRagEvalQuestionRole.PROMOTION_POOL,
                        )
                    )
            if questions:
                await repository.save_generated_questions(questions=tuple(questions))

            row = await pool.fetchrow(
                """
                WITH generated_per_entry AS (
                    SELECT
                        expected_runtime_entry_id,
                        COUNT(*) AS question_count
                    FROM knowledge_workbench_rag_eval_questions
                    WHERE run_id = $1
                      AND source = 'generated'
                    GROUP BY expected_runtime_entry_id
                )
                SELECT
                    COALESCE(SUM(question_count), 0) AS total_questions,
                    pg_typeof(COALESCE(SUM(question_count), 0))::text
                        AS total_questions_pg_type,
                    COUNT(*) AS represented_entry_count,
                    pg_typeof(COUNT(*))::text AS represented_entry_count_pg_type,
                    COUNT(*) FILTER (
                        WHERE question_count = $2
                    ) AS complete_entry_count,
                    pg_typeof(COUNT(*) FILTER (WHERE question_count = $2))::text
                        AS complete_entry_count_pg_type,
                    COUNT(*) FILTER (
                        WHERE question_count <> $2
                    ) AS incomplete_entry_count,
                    pg_typeof(COUNT(*) FILTER (WHERE question_count <> $2))::text
                        AS incomplete_entry_count_pg_type
                FROM generated_per_entry
                """,
                run_id,
                10,
            )
            assert row is not None
            assert row["total_questions_pg_type"] == "numeric"
            assert type(row["total_questions"]).__name__ == "Decimal"
            assert row["represented_entry_count_pg_type"] == "bigint"
            assert type(row["represented_entry_count"]).__name__ == "int"
            assert row["complete_entry_count_pg_type"] == "bigint"
            assert type(row["complete_entry_count"]).__name__ == "int"
            assert row["incomplete_entry_count_pg_type"] == "bigint"
            assert type(row["incomplete_entry_count"]).__name__ == "int"

            complete = await repository.has_complete_question_sets(
                rag_eval_run_id=run_id,
                expected_entry_count=len(question_counts_by_entry),
                questions_per_entry=10,
            )

            assert complete is expected_complete
        finally:
            await pool.close()
    finally:
        await _drop_database(base_database_url, database_name)


@pytest.mark.asyncio
async def test_migrated_postgres_accepts_all_v2_generated_question_kinds() -> None:
    base_database_url = os.getenv("DATABASE_URL")
    if not base_database_url:
        pytest.skip("DATABASE_URL is required for question kind constraint test")

    database_name = f"tmp_rag_eval_question_kinds_{uuid.uuid4().hex}"
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
            repository = PostgresWorkbenchRagEvalRepository(pool)
            project_id = str(uuid.uuid4())
            run_id = f"run-question-kinds-{uuid.uuid4().hex}"
            created_at = datetime(2026, 7, 15, 13, 0, tzinfo=timezone.utc)
            await repository.create_run(
                run=WorkbenchRagEvalRun(
                    run_id=run_id,
                    project_id=project_id,
                    publication_id=None,
                    source_document_ref=None,
                    status=WorkbenchRagEvalRunStatus.RUNNING,
                    question_generation_model="qwen/qwen3.6-27b",
                    question_generation_prompt_version="rag-eval-v2",
                    total_entries=len(RAG_EVAL_V2_GENERATED_QUESTION_KINDS),
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
                    updated_at=created_at,
                )
            )

            await repository.save_generated_questions(
                questions=tuple(
                    WorkbenchRagEvalQuestion(
                        question_id=f"question-kind:{kind.value}",
                        run_id=run_id,
                        project_id=project_id,
                        expected_runtime_entry_id=f"runtime-entry:{kind.value}",
                        expected_fact_id=f"fact:{kind.value}",
                        question=f"Question for {kind.value}?",
                        question_kind=kind,
                        source=WorkbenchRagEvalQuestionSource.GENERATED,
                        generation_model="qwen/qwen3.6-27b",
                        prompt_version="rag-eval-v2",
                        contract_version="workbench_rag_eval_questions.v2",
                        promotion_eligible=True,
                        ambiguity_risk=WorkbenchRagEvalQuestionAmbiguityRisk.LOW,
                        generation_rationale="constraint regression",
                        generation_account_ref="groq_org_primary",
                        generation_slot_index=0,
                        status=WorkbenchRagEvalQuestionStatus.CREATED,
                        created_at=created_at,
                        evaluation_role=WorkbenchRagEvalQuestionRole.PROMOTION_POOL,
                    )
                    for kind in RAG_EVAL_V2_GENERATED_QUESTION_KINDS
                )
            )

            rows = await pool.fetch(
                """
                SELECT question_kind
                FROM knowledge_workbench_rag_eval_questions
                WHERE run_id = $1
                ORDER BY question_kind
                """,
                run_id,
            )
            assert {row["question_kind"] for row in rows} == {
                kind.value for kind in RAG_EVAL_V2_GENERATED_QUESTION_KINDS
            }
        finally:
            await pool.close()
    finally:
        await _drop_database(base_database_url, database_name)


@pytest.mark.asyncio
async def test_workflow_command_failure_is_marked_after_aborted_transaction_rollback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base_database_url = os.getenv("DATABASE_URL")
    if not base_database_url:
        pytest.skip("DATABASE_URL is required for workflow command failure test")

    class AbortingDrain:
        async def execute(self, command, *, workflow_unit_of_work, **kwargs):
            del kwargs
            pending = await workflow_unit_of_work.command_log.list_pending_commands(
                workflow_run_id=command.workflow_run_id,
                limit=command.max_commands,
            )
            workflow_command = pending[0]
            try:
                await workflow_unit_of_work._connection.execute("SELECT 1 / 0")
            except Exception as exc:
                raise WorkbenchRagEvalWorkflowCommandHandlerFailed(
                    workflow_command=workflow_command,
                    cause=exc,
                ) from exc
            raise AssertionError("expected PostgreSQL error")

    database_name = f"tmp_rag_eval_command_failure_{uuid.uuid4().hex}"
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
            monkeypatch.setattr(
                runtime_module,
                "DrainWorkbenchRagEvalWorkflowCommands",
                AbortingDrain,
            )
            runtime = WorkbenchRagEvalWorkflowRuntimeComposition(
                pool=pool,
                llm_executor=SimpleNamespace(),
                prepare_llm_dispatch_batch=SimpleNamespace(),
                execute_prepared_llm_dispatch_attempt=SimpleNamespace(),
                search_published_workbench_runtime=SimpleNamespace(
                    embedding_generation_port=SimpleNamespace(),
                    embedding_model_id="test-embedding-model",
                    embedding_dimensions=384,
                ),
            )
            project_id = str(uuid.uuid4())
            run_id = f"run-command-failure-{uuid.uuid4().hex}"
            created_at = datetime(2026, 1, 1, 14, 0, tzinfo=timezone.utc)
            command_id = WorkflowCommandId(f"workflow-command:{run_id}:poison")
            await PostgresWorkbenchRagEvalRepository(pool).create_run(
                run=WorkbenchRagEvalRun(
                    run_id=run_id,
                    project_id=project_id,
                    publication_id=None,
                    source_document_ref=None,
                    status=WorkbenchRagEvalRunStatus.RUNNING,
                    question_generation_model="qwen/qwen3.6-27b",
                    question_generation_prompt_version="rag-eval-v2",
                    total_entries=1,
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
                    updated_at=created_at,
                )
            )
            connection = await pool.acquire()
            try:
                await PostgresCommandLogRepository(connection).append_pending_command(
                    WorkflowCommand(
                        command_id=command_id,
                        command_type=(
                            WorkbenchRagEvalWorkflowCommandType.RECONCILE_QUESTION_GENERATION_PROGRESS.value
                        ),
                        workflow_run_id=run_id,
                        idempotency_key=WorkflowIdempotencyKey(
                            f"rag-eval:{run_id}:poison"
                        ),
                        payload={
                            "workflow_run_id": run_id,
                            "rag_eval_run_id": run_id,
                            "project_id": project_id,
                        },
                        status=WorkflowCommandStatus.PENDING,
                        run_after=created_at,
                        created_at=created_at,
                        updated_at=created_at,
                    )
                )
            finally:
                await pool.release(connection)

            with pytest.raises(WorkbenchRagEvalWorkflowCommandHandlerFailed):
                await runtime.execute(workflow_run_id=run_id, max_commands=1)

            row = await pool.fetchrow(
                """
                SELECT status
                FROM workflow_runtime_command_log
                WHERE command_id = $1
                """,
                command_id.value,
            )
            assert row is not None
            assert row["status"] == WorkflowCommandStatus.FAILED.value
            assert await runtime._list_due_workflows(limit=10) == ()
        finally:
            await pool.close()
    finally:
        await _drop_database(base_database_url, database_name)


@pytest.mark.asyncio
async def test_rag_eval_question_generation_dispatch_payload_round_trips_through_postgres_jsonb() -> (
    None
):
    base_database_url = os.getenv("DATABASE_URL")
    if not base_database_url:
        pytest.skip("DATABASE_URL is required for dispatch JSONB round-trip test")

    database_name = f"tmp_rag_eval_dispatch_jsonb_{uuid.uuid4().hex}"
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
            project_id = str(uuid.uuid4())
            plan = WorkbenchRagEvalQuestionGenerationWorkPlanner(
                prompt_version="prompt-v1",
                generation_model_profile=model_budget_profile_for_ref("qwen/qwen3.6-27b"),
            ).plan(
                workflow_run_id="run-dispatch-jsonb",
                project_id=project_id,
                entries=(_rag_eval_entry(project_id=project_id),),
                provider_messages_by_runtime_entry_id={
                    "runtime-entry-1": (
                        {"role": "system", "content": "Generate eval questions."},
                        {"role": "user", "content": "Claim one with evidence."},
                    )
                },
            )

            await EnsureWorkItemsScheduled(
                repository=PostgresWorkItemSchedulingRepository(pool),
            ).execute(EnsureWorkItemsScheduledCommand(plans=plan))

            prepare_result = await PrepareLlmDispatchBatch(
                pool=pool,
                capacity_policy=CapacityAdmissionPolicy(),
                active_model_capacity_selector=SelectActiveLlmModelCapacity(
                    projector=ProjectLlmCapacityToCapacityRuntime(),
                ),
                route_catalog=workbench_rag_eval_route_catalog(),
                provider_account_refs=("groq_org_primary",),
                model_profiles=build_groq_free_plan_model_profiles(),
                dispatch_preparation_builder_registry=(
                    DispatchPreparationBuilderRegistry(
                        builders_by_work_kind={
                            WORKBENCH_RAG_EVAL_QUESTION_GENERATION_WORK_KIND: (
                                make_question_generation_dispatch_preparation_builder()
                            ),
                        }
                    )
                ),
            ).execute(
                PrepareLlmDispatchBatchCommand(
                    work_kind=WORKBENCH_RAG_EVAL_QUESTION_GENERATION_WORK_KIND,
                    requested_items=1,
                    worker=WorkerRef("rag-eval-jsonb-test"),
                    lease_token_prefix="rag-eval-jsonb-test",
                    lease_expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
                    now=datetime.now(timezone.utc),
                    started_at=datetime.now(timezone.utc),
                    active_model_ref="qwen/qwen3.6-27b",
                    provider_account_refs=("groq_org_primary",),
                )
            )
            assert len(prepare_result.attempt_result.started_attempts) == 1
            started_attempt = prepare_result.attempt_result.started_attempts[0]

            row = await pool.fetchrow(
                """
                SELECT dispatch_payload
                FROM execution_work_item_attempt_dispatches
                WHERE attempt_id = $1
                """,
                started_attempt.attempt_id,
            )
            assert row is not None
            raw_dispatch_payload = row["dispatch_payload"]
            dispatch_payload = (
                json.loads(raw_dispatch_payload)
                if isinstance(raw_dispatch_payload, str)
                else raw_dispatch_payload
            )
            assert isinstance(dispatch_payload, dict)
            estimate = dispatch_payload["schedule_payload"]["llm_capacity_estimate"]
            assert estimate["budget_contract_version"] == "v3"
            assert estimate["model_tpm_limit"] == 8_000

            transport = FakeGroqTransport()
            result = await GroqDispatchExecutor(
                transport=transport,
                model_profiles=build_groq_free_plan_model_profiles(),
            ).execute_dispatch(
                LlmDispatchExecutionInput(
                    attempt_id=started_attempt.attempt_id,
                    work_item_id=started_attempt.work_item_id,
                    attempt_number=started_attempt.attempt_number,
                    dispatch_payload=dispatch_payload,
                    started_at=datetime.now(timezone.utc),
                )
            )

            assert result.status is LlmDispatchExecutionStatus.SUCCEEDED
            assert transport.payloads
        finally:
            await pool.close()
    finally:
        await _drop_database(base_database_url, database_name)


@pytest.mark.asyncio
async def test_postgres_command_log_keeps_rag_eval_reconcile_prepare_idempotent() -> (
    None
):
    base_database_url = os.environ.get("DATABASE_URL")
    if not base_database_url:
        pytest.skip("DATABASE_URL is required for command-log idempotency test")

    maintenance_url = _database_url_with_database(base_database_url, "postgres")
    conn = await asyncpg.connect(maintenance_url)
    database_name = f"test_rag_eval_idempotency_{uuid.uuid4().hex[:12]}"
    try:
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
            occurred_at = datetime(2026, 7, 10, 12, tzinfo=timezone.utc)
            command_type = WorkbenchRagEvalWorkflowCommandType.PREPARE_QUESTION_GENERATION_DISPATCH_BATCH.value
            key = f"rag-eval:workflow-run-1:{command_type}:scheduled:8"
            payload = {
                "workflow_family": "workbench_rag_eval",
                "workflow_run_id": "workflow-run-1",
                "rag_eval_run_id": "workflow-run-1",
                "project_id": "project-1",
                "publication_id": "publication-1",
                "source_document_ref": "source-document-1",
                "work_kind": WORKBENCH_RAG_EVAL_QUESTION_GENERATION_WORK_KIND.value,
                "scheduled_work_item_count": 8,
            }
            async with pool.acquire() as connection:
                repository = PostgresCommandLogRepository(connection)
                first = await repository.append_pending_command(
                    WorkflowCommand(
                        command_id=WorkflowCommandId(f"workflow-command:{key}"),
                        command_type=command_type,
                        workflow_run_id="workflow-run-1",
                        idempotency_key=WorkflowIdempotencyKey(key),
                        payload=payload,
                        status=WorkflowCommandStatus.PENDING,
                        run_after=occurred_at,
                        created_at=occurred_at,
                        updated_at=occurred_at,
                    )
                )
                second = await repository.append_pending_command(
                    WorkflowCommand(
                        command_id=WorkflowCommandId(f"workflow-command:{key}:repeat"),
                        command_type=command_type,
                        workflow_run_id="workflow-run-1",
                        idempotency_key=WorkflowIdempotencyKey(key),
                        payload=payload,
                        status=WorkflowCommandStatus.PENDING,
                        run_after=occurred_at,
                        created_at=occurred_at,
                        updated_at=occurred_at,
                    )
                )
                with pytest.raises(ValueError, match="different payload"):
                    await repository.append_pending_command(
                        WorkflowCommand(
                            command_id=WorkflowCommandId(
                                f"workflow-command:{key}:mismatch"
                            ),
                            command_type=command_type,
                            workflow_run_id="workflow-run-1",
                            idempotency_key=WorkflowIdempotencyKey(key),
                            payload={
                                **payload,
                                "causation_dispatch_attempt_id": "must-not-be-here",
                            },
                            status=WorkflowCommandStatus.PENDING,
                            run_after=occurred_at,
                            created_at=occurred_at,
                            updated_at=occurred_at,
                        )
                    )

            assert second == first
        finally:
            await pool.close()
    finally:
        await _drop_database(base_database_url, database_name)


@pytest.mark.asyncio
async def test_qgen_reconcile_projects_frontend_event_and_updates_read_sides() -> None:
    base_database_url = os.environ.get("DATABASE_URL")
    if not base_database_url:
        pytest.skip("DATABASE_URL is required for qgen projection integration test")

    maintenance_url = _database_url_with_database(base_database_url, "postgres")
    conn = await asyncpg.connect(maintenance_url)
    database_name = f"test_rag_eval_qgen_projection_{uuid.uuid4().hex[:12]}"
    try:
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
            repository = PostgresWorkbenchRagEvalRepository(pool)
            project_id = str(uuid.uuid4())
            run_id = f"run-qgen-projection-{uuid.uuid4().hex}"
            occurred_at = datetime(2026, 7, 15, 14, 0, tzinfo=timezone.utc)
            await repository.create_run(
                run=WorkbenchRagEvalRun(
                    run_id=run_id,
                    project_id=project_id,
                    publication_id="publication-1",
                    source_document_ref=None,
                    status=WorkbenchRagEvalRunStatus.RUNNING,
                    question_generation_model="qwen/qwen3.6-27b",
                    question_generation_prompt_version="rag-eval-v2",
                    total_entries=1,
                    total_questions=0,
                    completed_questions=0,
                    top1_hits=0,
                    top3_hits=0,
                    top5_hits=0,
                    misses=0,
                    created_at=occurred_at,
                    started_at=occurred_at,
                    completed_at=None,
                    error_message=None,
                    current_phase=WorkbenchRagEvalCurrentPhase.QUESTION_GENERATION,
                    updated_at=occurred_at,
                )
            )
            await repository.save_generated_questions(
                questions=tuple(
                    WorkbenchRagEvalQuestion(
                        question_id=f"question:{run_id}:runtime-entry-1:{index}",
                        run_id=run_id,
                        project_id=project_id,
                        expected_runtime_entry_id="runtime-entry-1",
                        expected_fact_id="fact-1",
                        question=f"Generated question {index}?",
                        question_kind=WorkbenchRagEvalQuestionKind.DIRECT_PARAPHRASE,
                        source=WorkbenchRagEvalQuestionSource.GENERATED,
                        generation_model="qwen/qwen3.6-27b",
                        prompt_version="rag-eval-v2",
                        contract_version="workbench_rag_eval_questions.v2",
                        promotion_eligible=True,
                        ambiguity_risk=WorkbenchRagEvalQuestionAmbiguityRisk.LOW,
                        generation_rationale="projection regression",
                        generation_account_ref="groq_org_primary",
                        generation_slot_index=index,
                        status=WorkbenchRagEvalQuestionStatus.CREATED,
                        created_at=occurred_at,
                        evaluation_role=WorkbenchRagEvalQuestionRole.PROMOTION_POOL,
                    )
                    for index in range(10)
                )
            )

            current = WorkflowCommand(
                command_id=WorkflowCommandId(
                    f"workflow-command:{run_id}:qgen-reconcile"
                ),
                command_type=(
                    WorkbenchRagEvalWorkflowCommandType.RECONCILE_QUESTION_GENERATION_PROGRESS.value
                ),
                workflow_run_id=run_id,
                idempotency_key=WorkflowIdempotencyKey(
                    f"reconcile-rag-eval-question-generation:{run_id}:attempt-1"
                ),
                payload={
                    "workflow_family": "workbench_rag_eval",
                    "workflow_run_id": run_id,
                    "rag_eval_run_id": run_id,
                    "project_id": project_id,
                    "publication_id": "publication-1",
                    "work_kind": WORKBENCH_RAG_EVAL_QUESTION_GENERATION_WORK_KIND.value,
                    "causation_dispatch_attempt_id": "attempt-1",
                    "causation_work_item_id": "work-item-1",
                    "outcome_status": "succeeded",
                },
                status=WorkflowCommandStatus.PENDING,
                run_after=occurred_at,
                created_at=occurred_at,
                updated_at=occurred_at,
            )

            async with pool.acquire() as connection:
                unit_of_work = PostgresWorkflowRuntimeUnitOfWork(connection)
                await unit_of_work.start()
                await unit_of_work.command_log.append_pending_command(current)
                frontend_repository = PostgresFrontendWorkflowEventRepository(
                    connection
                )
                await HandleReconcileWorkbenchRagEvalQuestionGenerationProgressCommandHandler().execute(
                    HandleReconcileWorkbenchRagEvalQuestionGenerationProgressCommand(
                        current
                    ),
                    work_item_progress_read_repository=SimpleNamespace(
                        summarize_by_work_kind_and_workflow=AsyncMock(
                            return_value=WorkItemProgressSummary(
                                ready_count=0,
                                leased_count=0,
                                deferred_count=0,
                                retryable_failed_count=0,
                                completed_count=1,
                                terminal_failed_count=0,
                                cancelled_count=0,
                                split_superseded_count=0,
                                user_action_required_count=0,
                                total_count=1,
                                next_due_at=None,
                            )
                        )
                    ),
                    question_coverage_repository=repository,
                    rag_eval_repository=repository,
                    workflow_unit_of_work=unit_of_work,
                    frontend_event_projection_writer=ProjectFrontendWorkflowEvent(
                        projector=WorkbenchRagEvalFrontendWorkflowEventProjector(),
                        repository=frontend_repository,
                    ),
                )
                await unit_of_work.commit()

            questions = await repository.list_run_questions(
                project_id=project_id,
                run_id=run_id,
            )
            latest = await repository.get_latest_run(project_id=project_id)
            synthetic_document_id = f"rag-eval:{project_id}:{run_id}"
            async with pool.acquire() as connection:
                events = await PostgresFrontendWorkflowEventRepository(
                    connection
                ).list_frontend_events(
                    workflow_run_id=run_id,
                    after_cursor=FrontendWorkflowEventCursor.beginning(),
                    limit=20,
                )

            assert len(questions) == 10
            assert latest is not None
            assert (
                latest.current_phase
                is WorkbenchRagEvalCurrentPhase.RETRIEVAL_EVALUATION
            )
            assert any(
                event.projection_type
                == "rag_eval_question_generation_progress_reconciled"
                and event.document_id == synthetic_document_id
                for event in events
            )
        finally:
            await pool.close()
    finally:
        await _drop_database(base_database_url, database_name)
