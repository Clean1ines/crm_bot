from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

import asyncpg
import pytest

from src.domain.project_plane.knowledge_artifact_cleanup import (
    build_document_delete_cleanup_plan,
    build_document_reset_cleanup_plan,
    build_project_clear_cleanup_plan,
)
from src.infrastructure.db.repositories.knowledge_repository import KnowledgeRepository

pytestmark = pytest.mark.asyncio

TERMINAL_QUEUE_STATUS = "done"
NON_TERMINAL_QUEUE_STATUS = "pending"

DOCUMENT_ID_TABLES: tuple[str, ...] = (
    "knowledge_base",
    "knowledge_source_chunks",
    "knowledge_entries",
    "knowledge_entry_versions",
    "knowledge_edit_actions",
    "knowledge_retrieval_surface",
    "knowledge_compiler_runs",
    "knowledge_compiler_batches",
    "knowledge_answer_candidates",
    "knowledge_candidate_clusters",
    "knowledge_surface_compiler_runs",
    "knowledge_surface_compiler_stages",
    "knowledge_surface_source_units",
    "knowledge_surfaces",
    "knowledge_surface_relations",
    "knowledge_surface_local_relations",
    "knowledge_surface_global_relations",
    "knowledge_surface_candidates",
    "knowledge_surface_answer_drafts",
    "knowledge_surface_question_ownership",
    "knowledge_surface_question_reassignments",
    "knowledge_surface_merge_decisions",
    "knowledge_surface_rejected_questions",
    "knowledge_surface_reconciliation_runs",
    "rag_eval_datasets",
    "rag_eval_questions",
    "rag_eval_runs",
    "rag_eval_question_reviews",
    "rag_eval_review_groups",
)


@dataclass(frozen=True)
class ArtifactGraph:
    project_id: UUID
    user_id: UUID
    document_id: UUID
    source_chunk_id: str
    compiler_run_id: str
    compiler_batch_id: str
    candidate_id: str
    cluster_id: str
    entry_id: UUID
    edit_action_id: str
    surface_run_id: UUID
    surface_stage_id: UUID
    surface_source_unit_id: UUID
    surface_id: UUID
    surface_candidate_id: UUID
    surface_answer_draft_id: UUID
    rag_dataset_id: str
    rag_question_id: str
    rag_run_id: str
    rag_result_id: str
    non_terminal_job_id: UUID
    terminal_job_id: UUID


class SingleConnectionAcquire:
    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def __aenter__(self) -> asyncpg.Connection:
        return self._conn

    async def __aexit__(self, *_exc: object) -> None:
        return None


class SingleConnectionPool:
    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    def acquire(self) -> SingleConnectionAcquire:
        return SingleConnectionAcquire(self._conn)


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


def _vector_384() -> str:
    return "[" + ",".join("0" for _ in range(384)) + "]"


def _env_file_database_url() -> str | None:
    env_path = Path(".env")
    if not env_path.exists():
        return None

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or not line.startswith("DATABASE_URL="):
            continue
        return line.split("=", 1)[1].strip().strip('"').strip("'") or None

    return None


def _integration_dsn() -> str | None:
    dedicated_test_dsn = (
        os.getenv("TEST_DATABASE_URL")
        or os.getenv("TEST_DB_URL")
        or os.getenv("TEST_POSTGRES_DSN")
        or os.getenv("PYTEST_DATABASE_URL")
        or os.getenv("DATABASE_TEST_URL")
        or os.getenv("POSTGRES_TEST_DSN")
    )
    if dedicated_test_dsn:
        return dedicated_test_dsn

    if os.getenv("KAC_ALLOW_DEV_DATABASE_URL") == "1":
        return _env_file_database_url()

    return None


@pytest.fixture()
async def kac_conn() -> AsyncIterator[asyncpg.Connection]:
    if os.getenv("KAC_RUN_DB_INTEGRATION") != "1":
        pytest.skip("Set KAC_RUN_DB_INTEGRATION=1 to run real DB cleanup tests.")

    dsn = _integration_dsn()
    if not dsn:
        pytest.skip(
            "No safe integration DSN. Set TEST_* DSN or "
            "KAC_ALLOW_DEV_DATABASE_URL=1 for local crm_dev."
        )

    conn = await asyncpg.connect(dsn)
    current_database = str(await conn.fetchval("SELECT current_database()") or "")
    is_safe_test_database = "test" in current_database.lower()
    is_explicit_dev_database = (
        os.getenv("KAC_ALLOW_DEV_DATABASE_URL") == "1" and current_database == "crm_dev"
    )
    if not is_safe_test_database and not is_explicit_dev_database:
        await conn.close()
        pytest.skip(
            "Refusing to run cleanup integration tests outside test DB or "
            "explicit local crm_dev."
        )

    transaction = conn.transaction()
    await transaction.start()
    try:
        yield conn
    finally:
        await transaction.rollback()
        await conn.close()


@pytest.fixture()
def kac_repo(kac_conn: asyncpg.Connection) -> KnowledgeRepository:
    return KnowledgeRepository(SingleConnectionPool(kac_conn))


async def _table_exists(conn: asyncpg.Connection, table: str) -> bool:
    return bool(
        await conn.fetchval(
            """
            SELECT EXISTS (
              SELECT 1
              FROM information_schema.tables
              WHERE table_schema = 'public'
                AND table_name = $1
            )
            """,
            table,
        )
    )


async def _table_column_meta(
    conn: asyncpg.Connection,
    table: str,
) -> dict[str, dict[str, object]]:
    rows = await conn.fetch(
        """
        SELECT column_name, udt_name, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = $1
        ORDER BY ordinal_position
        """,
        table,
    )
    return {str(row["column_name"]): dict(row) for row in rows}


async def _constraint_literals(
    conn: asyncpg.Connection,
    constraint_name: str,
) -> tuple[str, ...]:
    definition = await conn.fetchval(
        """
        SELECT pg_get_constraintdef(oid)
        FROM pg_constraint
        WHERE conname = $1
        """,
        constraint_name,
    )
    if definition is None:
        return ()
    return tuple(dict.fromkeys(re.findall(r"'([^']+)'", str(definition))))


async def _checked_literal(
    conn: asyncpg.Connection,
    *,
    constraint_name: str,
    preferred: Sequence[str],
    fallback: str,
) -> str:
    allowed = await _constraint_literals(conn, constraint_name)
    if not allowed:
        return fallback
    for value in preferred:
        if value in allowed:
            return value
    return allowed[0]


def _json_default(column: str) -> str:
    if column in {
        "questions",
        "synonyms",
        "tags",
        "source_refs",
        "source_chunk_ids",
        "source_chunk_indexes",
        "target_entry_ids_json",
        "proposed_actions",
        "retrieved_entry_ids",
        "expected_entry_ids",
        "merged_surface_keys",
        "keep_separate_surface_keys",
        "children",
    }:
        return _json([])
    return _json({})


def _text_default(table: str, column: str) -> str:
    defaults: dict[str, str] = {
        "knowledge_base.entry_kind": "answer",
        "knowledge_entries.entry_kind": "answer",
        "knowledge_entries.status": "published",
        "knowledge_entries.visibility": "runtime",
        "knowledge_retrieval_surface.entry_kind": "answer",
        "knowledge_retrieval_surface.runtime_status": "published",
        "knowledge_retrieval_surface.runtime_visibility": "runtime",
        "knowledge_retrieval_surface.status": "published",
        "knowledge_retrieval_surface.visibility": "runtime",
        "knowledge_compiler_runs.mode": "faq",
        "knowledge_compiler_runs.compiler_version": "kac-test",
        "knowledge_compiler_runs.status": "completed",
        "knowledge_compiler_batches.status": "completed",
        "knowledge_answer_candidates.status": "extracted",
        "knowledge_candidate_clusters.status": "created",
        "knowledge_edit_actions.action_type": "hide_entry",
        "knowledge_edit_actions.status": "proposed",
        "knowledge_edit_actions.source_kind": "manual",
        "knowledge_surface_compiler_runs.compiler_kind": "faq_surface",
        "knowledge_surface_compiler_runs.mode": "faq",
        "knowledge_surface_compiler_runs.preprocessing_mode": "faq",
        "knowledge_surface_compiler_runs.status": "completed",
        "knowledge_surface_compiler_stages.stage_kind": "local_discovery",
        "knowledge_surface_compiler_stages.status": "completed",
        "knowledge_surfaces.surface_kind": "answer",
        "knowledge_surfaces.status": "ready",
        "knowledge_surfaces.publication_status": "unpublished",
        "knowledge_surface_relations.relation_kind": "related",
        "knowledge_surface_relations.relation_type": "related",
        "knowledge_surface_local_relations.relation_kind": "related",
        "knowledge_surface_local_relations.relation_type": "related",
        "knowledge_surface_global_relations.relation_kind": "related",
        "knowledge_surface_global_relations.relation_type": "related",
        "knowledge_surface_candidates.surface_kind": "answer",
        "knowledge_surface_question_ownership.question_kind": "canonical",
        "knowledge_surface_merge_decisions.decision": "keep_separate",
        "knowledge_surface_merge_decisions.decision_type": "keep_separate",
        "knowledge_surface_reconciliation_runs.status": "completed",
        "rag_eval_datasets.generator_version": "kac-test",
        "rag_eval_questions.question_type": "fact",
        "rag_eval_runs.status": "completed",
        "rag_eval_runs.runner_version": "kac-test",
        "rag_eval_question_reviews.status": "pending",
        "rag_eval_review_groups.status": "ready_for_review",
        "execution_queue.task_type": "process_knowledge_upload",
        "execution_queue.status": "pending",
    }
    return defaults.get(f"{table}.{column}", f"kac-{table}-{column}")


def _missing_required_default(
    *,
    table: str,
    column: str,
    udt_name: str,
) -> object:
    if column == "quote_hash":
        return hashlib.md5(b"KAC quote").hexdigest()
    if column in {
        "from_version",
        "to_version",
        "version",
        "batch_index",
        "batch_count",
    }:
        return 1
    if column.endswith("_count") or column in {
        "source_index",
        "candidate_index",
        "action_index",
        "attempts",
        "tokens_input",
        "tokens_output",
        "tokens_total",
        "input_candidate_count",
        "input_relation_count",
        "output_surface_count",
    }:
        return 0
    if column == "max_attempts":
        return 3
    if udt_name == "uuid":
        return uuid4()
    if udt_name == "jsonb":
        return _json_default(column)
    if udt_name in {"float4", "float8"}:
        return 1.0
    if udt_name == "bool":
        return False
    if udt_name in {"_int4", "_text", "_uuid"}:
        return []
    return _text_default(table, column)


def _placeholder(index: int, udt_name: str) -> str:
    if udt_name == "jsonb":
        return f"${index}::jsonb"
    if udt_name == "vector":
        return f"${index}::vector"
    if udt_name == "_int4":
        return f"${index}::int[]"
    if udt_name == "_text":
        return f"${index}::text[]"
    if udt_name == "_uuid":
        return f"${index}::uuid[]"
    return f"${index}"


async def _insert_row(
    conn: asyncpg.Connection,
    table: str,
    **values: object,
) -> None:
    meta = await _table_column_meta(conn, table)
    if not meta:
        pytest.fail(f"table `{table}` does not exist")

    insert_values: dict[str, object] = {
        column: value for column, value in values.items() if column in meta
    }

    for column, column_meta in meta.items():
        required = (
            column_meta["is_nullable"] == "NO" and column_meta["column_default"] is None
        )
        if required and column not in insert_values:
            insert_values[column] = _missing_required_default(
                table=table,
                column=column,
                udt_name=str(column_meta["udt_name"]),
            )

    columns = tuple(insert_values.keys())
    placeholders = tuple(
        _placeholder(index, str(meta[column]["udt_name"]))
        for index, column in enumerate(columns, start=1)
    )
    args = tuple(insert_values[column] for column in columns)

    try:
        await conn.execute(
            f"""
            INSERT INTO {table} ({", ".join(columns)})
            VALUES ({", ".join(placeholders)})
            """,
            *args,
        )
    except Exception as exc:
        pytest.fail(
            f"insert into `{table}` failed: {type(exc).__name__}: {exc}; "
            f"columns={columns}"
        )


async def _count(conn: asyncpg.Connection, sql: str, *args: object) -> int:
    return int(await conn.fetchval(sql, *args) or 0)


async def _count_document_id_table(
    conn: asyncpg.Connection,
    table: str,
    document_id: UUID,
) -> int:
    return await _count(
        conn,
        f"SELECT count(*) FROM {table} WHERE document_id = $1",
        document_id,
    )


async def _insert_user(conn: asyncpg.Connection, *, suffix: str) -> UUID:
    user_id = uuid4()
    await _insert_row(
        conn,
        "users",
        id=user_id,
        email=f"kac-{suffix}@example.test",
        username=f"kac-{suffix}",
        full_name=f"KAC User {suffix}",
        is_platform_admin=False,
    )
    return user_id


async def _insert_project(
    conn: asyncpg.Connection,
    *,
    user_id: UUID,
    suffix: str,
) -> UUID:
    project_id = uuid4()
    await _insert_row(
        conn,
        "projects",
        id=project_id,
        name=f"KAC Project {suffix}",
        user_id=user_id,
    )
    return project_id


async def _insert_project_with_user(
    conn: asyncpg.Connection,
    *,
    suffix: str,
) -> tuple[UUID, UUID]:
    user_id = await _insert_user(conn, suffix=suffix)
    project_id = await _insert_project(conn, user_id=user_id, suffix=suffix)
    return project_id, user_id


async def _insert_document(
    conn: asyncpg.Connection,
    *,
    project_id: UUID,
    user_id: UUID,
    suffix: str,
) -> UUID:
    document_id = uuid4()
    await _insert_row(
        conn,
        "knowledge_documents",
        id=document_id,
        project_id=project_id,
        file_name=f"kac-{suffix}.md",
        file_size=128,
        status="processed",
        uploaded_by=str(user_id),
        preprocessing_mode="faq",
        preprocessing_status="completed",
        preprocessing_error=None,
        preprocessing_model="kac-test-model",
        preprocessing_prompt_version="kac-test-prompt",
        preprocessing_metrics=_json({"stage": "completed"}),
    )
    return document_id


async def _insert_queue_job(
    conn: asyncpg.Connection,
    *,
    project_id: UUID,
    document_id: UUID,
    status: str,
    suffix: str,
) -> UUID:
    job_id = uuid4()
    await _insert_row(
        conn,
        "execution_queue",
        id=job_id,
        task_type="process_knowledge_upload",
        payload=_json(
            {
                "project_id": str(project_id),
                "document_id": str(document_id),
                "preprocessing_mode": "faq",
                "source": suffix,
            }
        ),
        status=status,
        attempts=0,
        max_attempts=3,
    )
    return job_id


async def _insert_artifact_graph(
    conn: asyncpg.Connection,
    *,
    project_id: UUID,
    user_id: UUID,
    document_id: UUID,
    suffix: str,
) -> ArtifactGraph:
    source_chunk_id = f"{document_id}:source:0"
    compiler_run_id = f"{document_id}:compiler-run"
    compiler_batch_id = f"{document_id}:compiler-batch"
    candidate_id = f"{document_id}:candidate"
    cluster_id = f"{document_id}:cluster"
    entry_id = uuid4()
    edit_action_id = f"{document_id}:edit-action"

    surface_run_id = uuid4()
    surface_stage_id = uuid4()
    surface_source_unit_id = uuid4()
    surface_id = uuid4()
    surface_candidate_id = uuid4()
    surface_answer_draft_id = uuid4()

    rag_dataset_id = f"{document_id}:dataset"
    rag_question_id = f"{document_id}:question"
    rag_run_id = f"{document_id}:rag-run"
    rag_result_id = f"{document_id}:rag-result"

    non_terminal_job_id = await _insert_queue_job(
        conn,
        project_id=project_id,
        document_id=document_id,
        status=NON_TERMINAL_QUEUE_STATUS,
        suffix=f"{suffix}-pending",
    )
    terminal_job_id = await _insert_queue_job(
        conn,
        project_id=project_id,
        document_id=document_id,
        status=TERMINAL_QUEUE_STATUS,
        suffix=f"{suffix}-terminal",
    )

    entry_kind = await _checked_literal(
        conn,
        constraint_name="ck_knowledge_entries_entry_kind",
        preferred=("answer", "faq_answer", "custom"),
        fallback="answer",
    )
    entry_status = await _checked_literal(
        conn,
        constraint_name="ck_knowledge_entries_status",
        preferred=("published", "embedded", "grounded"),
        fallback="published",
    )
    entry_visibility = await _checked_literal(
        conn,
        constraint_name="ck_knowledge_entries_visibility",
        preferred=("runtime", "internal"),
        fallback="runtime",
    )
    action_type = await _checked_literal(
        conn,
        constraint_name="ck_knowledge_edit_actions_action_type",
        preferred=("hide_entry", "attach_question_to_entry", "merge_entries"),
        fallback="hide_entry",
    )
    action_status = await _checked_literal(
        conn,
        constraint_name="ck_knowledge_edit_actions_status",
        preferred=("proposed", "in_progress", "applied"),
        fallback="proposed",
    )
    candidate_status = await _checked_literal(
        conn,
        constraint_name="ck_knowledge_answer_candidates_status",
        preferred=("extracted", "grounded_checked", "clustered"),
        fallback="extracted",
    )
    cluster_status = await _checked_literal(
        conn,
        constraint_name="ck_knowledge_candidate_clusters_status",
        preferred=("created", "clustered", "merged"),
        fallback="created",
    )

    await _insert_row(
        conn,
        "knowledge_base",
        id=uuid4(),
        project_id=project_id,
        document_id=document_id,
        content=f"KAC legacy content {suffix}",
        title=f"KAC legacy title {suffix}",
        source_excerpt=f"KAC source excerpt {suffix}",
        questions=_json([]),
        synonyms=_json([]),
        tags=_json([]),
        embedding_text=f"KAC embedding text {suffix}",
        entry_kind=entry_kind,
    )
    await _insert_row(
        conn,
        "knowledge_source_chunks",
        id=source_chunk_id,
        project_id=project_id,
        document_id=document_id,
        source_index=0,
        content=f"KAC source chunk {suffix}",
        page=None,
        section_title="",
        start_offset=0,
        end_offset=1,
        metadata=_json({}),
    )
    await _insert_row(
        conn,
        "knowledge_compiler_runs",
        id=compiler_run_id,
        project_id=project_id,
        document_id=document_id,
        mode="faq",
        compiler_version="kac-test",
        prompt_version="kac-test",
        model="kac-test-model",
        status="completed",
        metrics=_json({}),
        error="",
    )
    await _insert_row(
        conn,
        "knowledge_compilation_metrics",
        compiler_run_id=compiler_run_id,
        source_chunk_count=1,
        answer_candidate_count=1,
        grounded_candidate_count=1,
        rejected_candidate_count=0,
        candidate_cluster_count=1,
    )
    await _insert_row(
        conn,
        "knowledge_compiler_batches",
        id=compiler_batch_id,
        project_id=project_id,
        document_id=document_id,
        compiler_run_id=compiler_run_id,
        batch_index=1,
        batch_count=1,
        status="completed",
        input_text="input",
        output_text="output",
        tokens_input=1,
        tokens_output=1,
        tokens_total=2,
    )
    await _insert_row(
        conn,
        "knowledge_answer_candidates",
        id=candidate_id,
        project_id=project_id,
        document_id=document_id,
        compiler_run_id=compiler_run_id,
        topic_key=f"topic-{suffix}",
        title=f"KAC candidate {suffix}",
        candidate_answer=f"KAC answer candidate {suffix}",
        source_refs=_json([{"source_chunk_id": source_chunk_id, "source_index": 0}]),
        confidence=1.0,
        status=candidate_status,
        metadata=_json({}),
    )
    await _insert_row(
        conn,
        "knowledge_candidate_clusters",
        id=cluster_id,
        project_id=project_id,
        document_id=document_id,
        compiler_run_id=compiler_run_id,
        cluster_key=f"cluster-{suffix}",
        topic=f"KAC topic {suffix}",
        canonical_title=f"KAC canonical title {suffix}",
        canonical_answer=f"KAC canonical answer {suffix}",
        status=cluster_status,
        metadata=_json({}),
    )
    await _insert_row(
        conn,
        "knowledge_candidate_cluster_members",
        cluster_id=cluster_id,
        candidate_id=candidate_id,
        candidate_index=0,
    )
    await _insert_row(
        conn,
        "knowledge_entries",
        id=entry_id,
        project_id=project_id,
        document_id=document_id,
        compiler_run_id=compiler_run_id,
        stable_key=f"entry-{suffix}",
        entry_kind=entry_kind,
        title=f"KAC entry {suffix}",
        answer=f"KAC answer {suffix}",
        status=entry_status,
        visibility=entry_visibility,
        version=1,
        compiler_version="kac-test",
        embedding_text=f"KAC embedding entry {suffix}",
        embedding_text_version="kac-test",
        enrichment=_json({}),
        metadata=_json({}),
    )
    await _insert_row(
        conn,
        "knowledge_entry_source_refs",
        entry_id=entry_id,
        source_chunk_id=source_chunk_id,
        source_index=0,
        quote="KAC",
        quote_hash=hashlib.md5(f"KAC-{suffix}".encode()).hexdigest(),
        start_offset=0,
        end_offset=1,
        confidence=1.0,
        metadata=_json({}),
    )
    await _insert_row(
        conn,
        "knowledge_retrieval_surface",
        project_id=project_id,
        document_id=document_id,
        entry_id=entry_id,
        stable_key=f"runtime-{suffix}",
        entry_kind=entry_kind,
        title=f"KAC runtime {suffix}",
        answer=f"KAC runtime answer {suffix}",
        questions=_json([]),
        synonyms=_json([]),
        tags=_json([]),
        search_text=f"KAC runtime search {suffix}",
        embedding_text=f"KAC runtime embedding {suffix}",
        embedding=_vector_384(),
        runtime_status=entry_status,
        runtime_visibility=entry_visibility,
        status=entry_status,
        visibility=entry_visibility,
        metadata=_json({}),
    )

    await _insert_row(
        conn,
        "rag_eval_datasets",
        id=rag_dataset_id,
        project_id=project_id,
        document_id=document_id,
        generator_version="kac-test",
        metadata=_json({}),
    )
    await _insert_row(
        conn,
        "rag_eval_questions",
        id=rag_question_id,
        dataset_id=rag_dataset_id,
        project_id=project_id,
        document_id=document_id,
        question=f"KAC eval question {suffix}?",
        expected_answer=f"KAC expected answer {suffix}",
        question_type="fact",
        source_chunk_ids=_json([source_chunk_id]),
        expected_entry_ids=_json([str(entry_id)]),
        metadata=_json({}),
    )
    await _insert_row(
        conn,
        "rag_eval_runs",
        id=rag_run_id,
        dataset_id=rag_dataset_id,
        project_id=project_id,
        document_id=document_id,
        status="completed",
        runner_version="kac-test",
        metrics=_json({}),
    )
    await _insert_row(
        conn,
        "rag_eval_results",
        id=rag_result_id,
        run_id=rag_run_id,
        question_id=rag_question_id,
        retrieved_answer=f"KAC retrieved answer {suffix}",
        expected_answer=f"KAC expected answer {suffix}",
        is_passed=True,
        score=1.0,
        notes="",
        retrieved_chunk_ids=_json([source_chunk_id]),
        expected_entry_ids=_json([str(entry_id)]),
        retrieved_entry_ids=_json([str(entry_id)]),
        classification=_json({}),
        proposed_actions=_json([]),
        metadata=_json({}),
    )
    await _insert_row(
        conn,
        "knowledge_edit_actions",
        id=edit_action_id,
        project_id=project_id,
        document_id=document_id,
        source_kind="rag_eval",
        source_result_id=rag_result_id,
        source_run_id=rag_run_id,
        source_question_id=rag_question_id,
        action_index=0,
        action_type=action_type,
        status=action_status,
        target_entry_id=entry_id,
        target_entry_ids_json=_json([str(entry_id)]),
        payload=_json({}),
        result_payload=_json({}),
        idempotency_key=f"kac-action-{suffix}",
    )
    await _insert_row(
        conn,
        "knowledge_entry_versions",
        id=uuid4(),
        entry_id=entry_id,
        project_id=project_id,
        document_id=document_id,
        action_id=edit_action_id,
        from_version=1,
        to_version=1,
        previous_snapshot=_json({}),
        new_snapshot=_json({"title": f"KAC entry {suffix}"}),
    )

    local_surface_key = f"{document_id}:surface"
    child_surface_key = f"{document_id}:surface-child"
    await _insert_row(
        conn,
        "knowledge_surface_compiler_runs",
        id=surface_run_id,
        project_id=project_id,
        document_id=document_id,
        compiler_kind="faq_surface",
        mode="faq",
        preprocessing_mode="faq",
        compiler_version="kac-test",
        prompt_version="kac-test",
        model="kac-test-model",
        status="completed",
        metrics=_json({"checkpoint_reused": False}),
    )
    await _insert_row(
        conn,
        "knowledge_surface_compiler_stages",
        id=surface_stage_id,
        run_id=surface_run_id,
        document_id=document_id,
        stage_kind="local_discovery",
        stage_index=0,
        status="completed",
        input_summary="input",
        output_summary="output",
        metrics=_json({}),
    )
    await _insert_row(
        conn,
        "knowledge_surface_source_units",
        id=surface_source_unit_id,
        run_id=surface_run_id,
        document_id=document_id,
        source_unit_key=f"unit-{suffix}",
        source_chunk_indexes=[0],
        title=f"KAC source unit {suffix}",
        body=f"KAC source unit body {suffix}",
        children=_json([]),
        metadata=_json({}),
    )
    await _insert_row(
        conn,
        "knowledge_surfaces",
        id=surface_id,
        run_id=surface_run_id,
        document_id=document_id,
        source_unit_id=surface_source_unit_id,
        local_surface_key=local_surface_key,
        surface_kind="answer",
        title=f"KAC surface {suffix}",
        canonical_question=f"KAC surface question {suffix}?",
        short_answer=f"KAC short answer {suffix}",
        answer=f"KAC surface answer {suffix}",
        questions=_json([f"KAC surface question {suffix}?"]),
        source_refs=_json([]),
        answer_scope="local",
        question_scope="local",
        exclusion_scope="",
        status="ready",
        publication_status="unpublished",
        metadata=_json({}),
    )
    await _insert_row(
        conn,
        "knowledge_surface_relations",
        id=uuid4(),
        run_id=surface_run_id,
        document_id=document_id,
        parent_surface_key=local_surface_key,
        child_surface_key=child_surface_key,
        relation_kind="related",
        relation_type="related",
        confidence=1.0,
        metadata=_json({}),
    )
    await _insert_row(
        conn,
        "knowledge_surface_local_relations",
        id=uuid4(),
        run_id=surface_run_id,
        document_id=document_id,
        source_unit_id=surface_source_unit_id,
        source_surface_key=local_surface_key,
        target_surface_key=child_surface_key,
        relation_kind="related",
        relation_type="related",
        reason="test",
        metadata=_json({}),
    )
    await _insert_row(
        conn,
        "knowledge_surface_global_relations",
        id=uuid4(),
        run_id=surface_run_id,
        document_id=document_id,
        parent_surface_key=local_surface_key,
        child_surface_key=child_surface_key,
        relation_kind="related",
        relation_type="related",
        reason="test",
        metadata=_json({}),
    )
    await _insert_row(
        conn,
        "knowledge_surface_question_ownership",
        id=uuid4(),
        run_id=surface_run_id,
        document_id=document_id,
        question=f"KAC owned question {suffix}?",
        question_kind="canonical",
        owner_surface_key=local_surface_key,
        confidence=1.0,
        reason="test",
        metadata=_json({}),
    )
    await _insert_row(
        conn,
        "knowledge_surface_question_reassignments",
        id=uuid4(),
        run_id=surface_run_id,
        document_id=document_id,
        question=f"KAC reassigned question {suffix}?",
        from_surface_key=child_surface_key,
        to_surface_key=local_surface_key,
        reason="test",
        metadata=_json({}),
    )
    await _insert_row(
        conn,
        "knowledge_surface_merge_decisions",
        id=uuid4(),
        run_id=surface_run_id,
        document_id=document_id,
        left_surface_key=local_surface_key,
        right_surface_key=child_surface_key,
        survivor_surface_key=local_surface_key,
        candidate_surface_key=child_surface_key,
        target_surface_key=local_surface_key,
        decision="keep_separate",
        decision_type="keep_separate",
        reason="test",
        merged_surface_keys=_json([]),
        keep_separate_surface_keys=_json([local_surface_key, child_surface_key]),
        metadata=_json({}),
    )
    await _insert_row(
        conn,
        "knowledge_surface_candidates",
        id=surface_candidate_id,
        run_id=surface_run_id,
        document_id=document_id,
        source_unit_id=surface_source_unit_id,
        local_surface_key=local_surface_key,
        provisional_title=f"KAC candidate surface {suffix}",
        surface_kind="answer",
        answer_scope="local",
        question_scope="local",
        exclusion_scope="",
        metadata=_json({}),
    )
    await _insert_row(
        conn,
        "knowledge_surface_answer_drafts",
        id=surface_answer_draft_id,
        run_id=surface_run_id,
        document_id=document_id,
        candidate_key=f"draft-{suffix}",
        title=f"KAC draft {suffix}",
        canonical_question=f"KAC draft question {suffix}?",
        short_answer=f"KAC draft short {suffix}",
        answer=f"KAC draft answer {suffix}",
        answer_scope="local",
        question_scope="local",
        exclusion_scope="",
        metadata=_json({}),
    )
    await _insert_row(
        conn,
        "knowledge_surface_rejected_questions",
        id=uuid4(),
        run_id=surface_run_id,
        document_id=document_id,
        surface_key=local_surface_key,
        belongs_to_surface_key=local_surface_key,
        question=f"KAC rejected question {suffix}?",
        reason="test",
        metadata=_json({}),
    )
    await _insert_row(
        conn,
        "knowledge_surface_reconciliation_runs",
        id=uuid4(),
        project_id=project_id,
        document_id=document_id,
        run_id=surface_run_id,
        input_candidate_count=1,
        input_relation_count=1,
        output_surface_count=1,
        status="completed",
        metrics=_json({}),
    )
    rag_question_review_status = await _checked_literal(
        conn,
        constraint_name="ck_rag_eval_question_reviews_status",
        preferred=("ready_for_review", "accepted", "edited", "rejected", "approved"),
        fallback="ready_for_review",
    )
    rag_review_group_status = await _checked_literal(
        conn,
        constraint_name="ck_rag_eval_review_groups_status",
        preferred=("ready_for_review", "accepted", "rejected", "failed"),
        fallback="ready_for_review",
    )

    await _insert_row(
        conn,
        "rag_eval_question_reviews",
        id=f"{document_id}:question-review",
        question_id=rag_question_id,
        run_id=rag_run_id,
        dataset_id=rag_dataset_id,
        project_id=project_id,
        document_id=document_id,
        status=rag_question_review_status,
        original_question=f"KAC eval question {suffix}?",
        edited_question=f"KAC eval question {suffix}?",
        metadata=_json({}),
    )
    await _insert_row(
        conn,
        "rag_eval_review_groups",
        id=f"{document_id}:review-group",
        run_id=rag_run_id,
        dataset_id=rag_dataset_id,
        project_id=project_id,
        document_id=document_id,
        source_chunk_id=source_chunk_id,
        status=rag_review_group_status,
        question_count=1,
        accepted_count=0,
        rejected_count=0,
        payload=_json({}),
    )

    if await _table_exists(conn, "rag_quality_reports"):
        await _insert_row(
            conn,
            "rag_quality_reports",
            id=f"{document_id}:quality-report",
            run_id=rag_run_id,
            dataset_id=rag_dataset_id,
            project_id=project_id,
            document_id=document_id,
            summary=_json({}),
            metrics=_json({}),
        )

    return ArtifactGraph(
        project_id=project_id,
        user_id=user_id,
        document_id=document_id,
        source_chunk_id=source_chunk_id,
        compiler_run_id=compiler_run_id,
        compiler_batch_id=compiler_batch_id,
        candidate_id=candidate_id,
        cluster_id=cluster_id,
        entry_id=entry_id,
        edit_action_id=edit_action_id,
        surface_run_id=surface_run_id,
        surface_stage_id=surface_stage_id,
        surface_source_unit_id=surface_source_unit_id,
        surface_id=surface_id,
        surface_candidate_id=surface_candidate_id,
        surface_answer_draft_id=surface_answer_draft_id,
        rag_dataset_id=rag_dataset_id,
        rag_question_id=rag_question_id,
        rag_run_id=rag_run_id,
        rag_result_id=rag_result_id,
        non_terminal_job_id=non_terminal_job_id,
        terminal_job_id=terminal_job_id,
    )


async def _assert_document_artifacts_gone(
    conn: asyncpg.Connection,
    graph: ArtifactGraph,
    *,
    expect_document_exists: bool,
) -> None:
    expected_document_count = 1 if expect_document_exists else 0
    assert (
        await _count(
            conn,
            "SELECT count(*) FROM knowledge_documents WHERE id = $1",
            graph.document_id,
        )
        == expected_document_count
    )

    for table in DOCUMENT_ID_TABLES:
        assert await _count_document_id_table(conn, table, graph.document_id) == 0, (
            table
        )

    assert (
        await _count(
            conn,
            """
            SELECT count(*)
            FROM knowledge_entry_source_refs
            WHERE entry_id = $1 OR source_chunk_id = $2
            """,
            graph.entry_id,
            graph.source_chunk_id,
        )
        == 0
    )
    assert (
        await _count(
            conn,
            "SELECT count(*) FROM knowledge_compilation_metrics WHERE compiler_run_id = $1",
            graph.compiler_run_id,
        )
        == 0
    )
    assert (
        await _count(
            conn,
            """
            SELECT count(*)
            FROM knowledge_candidate_cluster_members
            WHERE cluster_id = $1 OR candidate_id = $2
            """,
            graph.cluster_id,
            graph.candidate_id,
        )
        == 0
    )
    assert (
        await _count(
            conn,
            """
            SELECT count(*)
            FROM rag_eval_results
            WHERE id = $1 OR run_id = $2 OR question_id = $3
            """,
            graph.rag_result_id,
            graph.rag_run_id,
            graph.rag_question_id,
        )
        == 0
    )

    non_terminal_status = await conn.fetchval(
        "SELECT status FROM execution_queue WHERE id = $1",
        graph.non_terminal_job_id,
    )
    terminal_status = await conn.fetchval(
        "SELECT status FROM execution_queue WHERE id = $1",
        graph.terminal_job_id,
    )
    assert non_terminal_status == "cancelled"
    assert terminal_status == TERMINAL_QUEUE_STATUS


async def _assert_control_graph_untouched(
    conn: asyncpg.Connection,
    graph: ArtifactGraph,
) -> None:
    assert (
        await _count(
            conn, "SELECT count(*) FROM projects WHERE id = $1", graph.project_id
        )
        == 1
    )
    assert (
        await _count(
            conn,
            "SELECT count(*) FROM knowledge_documents WHERE id = $1",
            graph.document_id,
        )
        == 1
    )
    for table in DOCUMENT_ID_TABLES:
        assert await _count_document_id_table(conn, table, graph.document_id) > 0, table


async def _assert_resume_artifacts_preserved(
    conn: asyncpg.Connection,
    graph: ArtifactGraph,
) -> None:
    assert (
        await _count(
            conn,
            "SELECT count(*) FROM knowledge_surface_compiler_runs WHERE id = $1",
            graph.surface_run_id,
        )
        == 1
    )
    assert (
        await _count(
            conn,
            "SELECT count(*) FROM knowledge_surface_source_units WHERE id = $1",
            graph.surface_source_unit_id,
        )
        == 1
    )
    assert (
        await _count(
            conn,
            "SELECT count(*) FROM knowledge_source_chunks WHERE id = $1",
            graph.source_chunk_id,
        )
        == 1
    )


async def test_cleanup_document_artifacts_removes_document_artifacts_without_touching_other_project(
    kac_conn: asyncpg.Connection,
    kac_repo: KnowledgeRepository,
) -> None:
    project_a, user_a = await _insert_project_with_user(kac_conn, suffix="doc-reset-a")
    project_b, user_b = await _insert_project_with_user(kac_conn, suffix="doc-reset-b")
    document_a = await _insert_document(
        kac_conn,
        project_id=project_a,
        user_id=user_a,
        suffix="doc-reset-a",
    )
    document_b = await _insert_document(
        kac_conn,
        project_id=project_b,
        user_id=user_b,
        suffix="doc-reset-b",
    )
    graph_a = await _insert_artifact_graph(
        kac_conn,
        project_id=project_a,
        user_id=user_a,
        document_id=document_a,
        suffix="doc-reset-a",
    )
    graph_b = await _insert_artifact_graph(
        kac_conn,
        project_id=project_b,
        user_id=user_b,
        document_id=document_b,
        suffix="doc-reset-b",
    )

    await kac_repo.cleanup_document_artifacts(
        build_document_reset_cleanup_plan(
            project_id=str(project_a),
            document_id=str(document_a),
        )
    )

    await _assert_document_artifacts_gone(
        kac_conn,
        graph_a,
        expect_document_exists=True,
    )
    await _assert_control_graph_untouched(kac_conn, graph_b)


async def test_cleanup_document_delete_plan_removes_document_row_and_artifacts(
    kac_conn: asyncpg.Connection,
    kac_repo: KnowledgeRepository,
) -> None:
    project_a, user_a = await _insert_project_with_user(kac_conn, suffix="doc-delete-a")
    project_b, user_b = await _insert_project_with_user(kac_conn, suffix="doc-delete-b")
    document_a = await _insert_document(
        kac_conn,
        project_id=project_a,
        user_id=user_a,
        suffix="doc-delete-a",
    )
    document_b = await _insert_document(
        kac_conn,
        project_id=project_b,
        user_id=user_b,
        suffix="doc-delete-b",
    )
    graph_a = await _insert_artifact_graph(
        kac_conn,
        project_id=project_a,
        user_id=user_a,
        document_id=document_a,
        suffix="doc-delete-a",
    )
    graph_b = await _insert_artifact_graph(
        kac_conn,
        project_id=project_b,
        user_id=user_b,
        document_id=document_b,
        suffix="doc-delete-b",
    )

    await kac_repo.cleanup_document_artifacts(
        build_document_delete_cleanup_plan(
            project_id=str(project_a),
            document_id=str(document_a),
        )
    )

    await _assert_document_artifacts_gone(
        kac_conn,
        graph_a,
        expect_document_exists=False,
    )
    await _assert_control_graph_untouched(kac_conn, graph_b)


async def test_cleanup_project_artifacts_removes_all_project_knowledge_artifacts(
    kac_conn: asyncpg.Connection,
    kac_repo: KnowledgeRepository,
) -> None:
    project_a, user_a = await _insert_project_with_user(
        kac_conn, suffix="project-clear-a"
    )
    project_b, user_b = await _insert_project_with_user(
        kac_conn, suffix="project-clear-b"
    )
    document_a1 = await _insert_document(
        kac_conn,
        project_id=project_a,
        user_id=user_a,
        suffix="project-clear-a1",
    )
    document_a2 = await _insert_document(
        kac_conn,
        project_id=project_a,
        user_id=user_a,
        suffix="project-clear-a2",
    )
    document_b = await _insert_document(
        kac_conn,
        project_id=project_b,
        user_id=user_b,
        suffix="project-clear-b",
    )
    graph_a1 = await _insert_artifact_graph(
        kac_conn,
        project_id=project_a,
        user_id=user_a,
        document_id=document_a1,
        suffix="project-clear-a1",
    )
    graph_a2 = await _insert_artifact_graph(
        kac_conn,
        project_id=project_a,
        user_id=user_a,
        document_id=document_a2,
        suffix="project-clear-a2",
    )
    graph_b = await _insert_artifact_graph(
        kac_conn,
        project_id=project_b,
        user_id=user_b,
        document_id=document_b,
        suffix="project-clear-b",
    )

    await kac_repo.cleanup_project_artifacts(
        build_project_clear_cleanup_plan(project_id=str(project_a))
    )

    await _assert_document_artifacts_gone(
        kac_conn,
        graph_a1,
        expect_document_exists=False,
    )
    await _assert_document_artifacts_gone(
        kac_conn,
        graph_a2,
        expect_document_exists=False,
    )
    assert (
        await _count(kac_conn, "SELECT count(*) FROM projects WHERE id = $1", project_a)
        == 1
    )
    await _assert_control_graph_untouched(kac_conn, graph_b)


async def test_delete_document_chunks_wrapper_uses_reset_cleanup_semantics(
    kac_conn: asyncpg.Connection,
    kac_repo: KnowledgeRepository,
) -> None:
    project_id, user_id = await _insert_project_with_user(
        kac_conn, suffix="wrapper-reset"
    )
    document_id = await _insert_document(
        kac_conn,
        project_id=project_id,
        user_id=user_id,
        suffix="wrapper-reset",
    )
    graph = await _insert_artifact_graph(
        kac_conn,
        project_id=project_id,
        user_id=user_id,
        document_id=document_id,
        suffix="wrapper-reset",
    )

    await kac_repo.delete_document_chunks(str(document_id))

    await _assert_document_artifacts_gone(
        kac_conn,
        graph,
        expect_document_exists=True,
    )


async def test_delete_document_wrapper_uses_delete_cleanup_semantics(
    kac_conn: asyncpg.Connection,
    kac_repo: KnowledgeRepository,
) -> None:
    project_id, user_id = await _insert_project_with_user(
        kac_conn, suffix="wrapper-delete"
    )
    document_id = await _insert_document(
        kac_conn,
        project_id=project_id,
        user_id=user_id,
        suffix="wrapper-delete",
    )
    graph = await _insert_artifact_graph(
        kac_conn,
        project_id=project_id,
        user_id=user_id,
        document_id=document_id,
        suffix="wrapper-delete",
    )

    await kac_repo.delete_document(str(document_id))

    await _assert_document_artifacts_gone(
        kac_conn,
        graph,
        expect_document_exists=False,
    )


async def test_clear_project_knowledge_wrapper_uses_project_cleanup_semantics(
    kac_conn: asyncpg.Connection,
    kac_repo: KnowledgeRepository,
) -> None:
    project_id, user_id = await _insert_project_with_user(
        kac_conn, suffix="wrapper-project"
    )
    document_id = await _insert_document(
        kac_conn,
        project_id=project_id,
        user_id=user_id,
        suffix="wrapper-project",
    )
    graph = await _insert_artifact_graph(
        kac_conn,
        project_id=project_id,
        user_id=user_id,
        document_id=document_id,
        suffix="wrapper-project",
    )

    await kac_repo.clear_project_knowledge(str(project_id))

    await _assert_document_artifacts_gone(
        kac_conn,
        graph,
        expect_document_exists=False,
    )
    assert (
        await _count(
            kac_conn, "SELECT count(*) FROM projects WHERE id = $1", project_id
        )
        == 1
    )


async def test_manual_cancel_preserves_surface_resume_artifacts(
    kac_conn: asyncpg.Connection,
    kac_repo: KnowledgeRepository,
) -> None:
    project_id, user_id = await _insert_project_with_user(
        kac_conn, suffix="manual-cancel"
    )
    document_id = await _insert_document(
        kac_conn,
        project_id=project_id,
        user_id=user_id,
        suffix="manual-cancel",
    )
    graph = await _insert_artifact_graph(
        kac_conn,
        project_id=project_id,
        user_id=user_id,
        document_id=document_id,
        suffix="manual-cancel",
    )

    cancelled = await kac_repo.cancel_document_processing(
        project_id=str(project_id),
        document_id=str(document_id),
        reason="Остановлено пользователем",
    )

    assert cancelled is True
    await _assert_resume_artifacts_preserved(kac_conn, graph)


async def test_quota_pause_preserves_auto_resume_artifacts(
    kac_conn: asyncpg.Connection,
) -> None:
    project_id, user_id = await _insert_project_with_user(
        kac_conn, suffix="quota-pause"
    )
    document_id = await _insert_document(
        kac_conn,
        project_id=project_id,
        user_id=user_id,
        suffix="quota-pause",
    )
    graph = await _insert_artifact_graph(
        kac_conn,
        project_id=project_id,
        user_id=user_id,
        document_id=document_id,
        suffix="quota-pause",
    )

    await kac_conn.execute(
        """
        UPDATE knowledge_documents
        SET status = 'error',
            preprocessing_status = 'failed',
            preprocessing_metrics = $2::jsonb
        WHERE id = $1
        """,
        document_id,
        _json(
            {
                "stage": "processing_paused_quota",
                "status": "processing_paused_quota",
                "retry_after_seconds": 60,
            }
        ),
    )

    await _assert_resume_artifacts_preserved(kac_conn, graph)
