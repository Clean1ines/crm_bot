from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
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
    WorkbenchRagEvalRun,
    WorkbenchRagEvalRunProgress,
    WorkbenchRagEvalRunStatus,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.plan_workbench_rag_eval_question_generation_work import (
    WorkbenchRagEvalQuestionGenerationWorkPlanner,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.workbench_rag_eval_dispatch_preparation import (
    make_question_generation_dispatch_preparation_builder,
    workbench_rag_eval_route_catalog,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.workbench_rag_eval_work_kinds import (
    WORKBENCH_RAG_EVAL_QUESTION_GENERATION_WORK_KIND,
)
from src.contexts.knowledge_workbench.rag_eval.infrastructure.postgres.postgres_workbench_rag_eval_repository import (
    PostgresWorkbenchRagEvalRepository,
)
from src.contexts.knowledge_workbench.retrieval.application.models.published_workbench_retrieval import (
    PublishedWorkbenchRetrievalResult,
    PublishedWorkbenchRetrievalSourceRef,
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
                generation_model_profile=model_budget_profile_for_ref("qwen/qwen3-32b"),
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
                    active_model_ref="qwen/qwen3-32b",
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
            assert estimate["model_tpm_limit"] == 6_000

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
