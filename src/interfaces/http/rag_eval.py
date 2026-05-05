from __future__ import annotations

from typing import Annotated, Literal, TypedDict, cast

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.application.rag_eval.dataset_generator import LlmRagEvalDatasetGenerator
from src.application.rag_eval.judge import LlmRagEvalAnswerJudge
from src.application.rag_eval.reporter import RagQualityReporter
from src.application.rag_eval.runner import RagEvalRunner
from src.application.rag_eval.service import RagEvalService
from src.domain.project_plane.json_types import JsonValue
from src.infrastructure.config.settings import settings
from src.infrastructure.db.repositories.knowledge_repository import KnowledgeRepository
from src.infrastructure.db.repositories.project import ProjectRepository
from src.infrastructure.db.repositories.queue_repository import QueueRepository
from src.infrastructure.db.repositories.rag_eval_repository import RagEvalRepository
from src.infrastructure.db.repositories.user_repository import UserRepository
from src.infrastructure.llm.query_expander import GroqQueryExpander
from src.infrastructure.llm.rag_contract import KnowledgeSearchRepository
from src.infrastructure.llm.rag_service import RAGService
from src.infrastructure.queue.job_types import TASK_RUN_FULL_RAG_EVAL
from src.infrastructure.rag_eval.adapters import (
    GroqRagEvalJsonLlmAdapter,
    RagServiceRagEvalRetriever,
)
from src.interfaces.composition.rag_eval_answerer import ProductionRagEvalAnswerer
from src.interfaces.http.dependencies import (
    get_current_user_id,
    get_pool,
    get_queue_repo,
    get_project_repo,
    get_user_repository,
)


router = APIRouter(prefix="/api/rag-eval", tags=["rag-eval"])

RagEvalMode = Literal["quick", "standard", "deep", "paranoid"]

MODE_LIMITS: dict[RagEvalMode, int] = {
    "quick": 30,
    "standard": 75,
    "deep": 200,
    "paranoid": 500,
}

PROJECT_RAG_EVAL_ROLES = ["owner", "admin"]
RAG_EVAL_GROQ_MODEL = "llama-3.1-8b-instant"

ModeQuery = Annotated[
    str,
    Query(
        description="RAG eval mode.",
        pattern="^(quick|standard|deep|paranoid)$",
    ),
]
MaxQuestionsQuery = Annotated[
    int | None,
    Query(
        ge=1,
        le=500,
        description="Override question count. Keep small for HTTP smoke tests.",
    ),
]


QuestionsPerChunkQuery = Annotated[
    int,
    Query(
        ge=1,
        le=5,
        description="Full-document eval density. 1 means at least one generated eval question per source chunk.",
    ),
]
MaxFullQuestionsQuery = Annotated[
    int | None,
    Query(
        ge=1,
        le=50000,
        description="Optional hard cap for full-document eval. Leave empty to cover the whole document.",
    ),
]


class DocumentHealth(TypedDict):
    id: str
    project_id: str
    status: str
    file_name: str
    chunk_count: int


def _require_groq_key() -> None:
    if not settings.GROQ_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GROQ_API_KEY is not configured",
        )


def _mode_value(mode: str) -> RagEvalMode:
    if mode == "quick":
        return "quick"
    if mode == "standard":
        return "standard"
    if mode == "deep":
        return "deep"
    if mode == "paranoid":
        return "paranoid"

    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="mode must be one of: quick, standard, deep, paranoid",
    )


def _question_limit(mode: str, max_questions: int | None) -> int:
    parsed_mode = _mode_value(mode)
    return max_questions if max_questions is not None else MODE_LIMITS[parsed_mode]


async def _require_project_rag_eval_access(
    *,
    project_id: str,
    current_user_id: str,
    project_repo: ProjectRepository,
    user_repo: UserRepository,
) -> None:
    if await user_repo.is_platform_admin(current_user_id):
        return

    if await project_repo.user_has_project_role(
        project_id,
        current_user_id,
        PROJECT_RAG_EVAL_ROLES,
    ):
        return

    project = await project_repo.get_project_view(project_id)
    if project and project.user_id == current_user_id:
        return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Project admin access required",
    )


async def _latest_processed_document_id(pool: asyncpg.Pool) -> str:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT d.id
            FROM knowledge_documents AS d
            WHERE d.status = 'processed'
              AND EXISTS (
                  SELECT 1
                  FROM knowledge_base AS kb
                  WHERE kb.document_id = d.id
              )
            ORDER BY d.created_at DESC, d.id DESC
            LIMIT 1
            """
        )

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No processed knowledge document with chunks found",
        )
    return str(row["id"])


async def _resolve_document_id(pool: asyncpg.Pool, document_id: str) -> str:
    if document_id in {"latest", "--latest"}:
        return await _latest_processed_document_id(pool)
    return document_id


async def _document_health(
    pool: asyncpg.Pool,
    document_id: str,
) -> DocumentHealth:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                d.id,
                d.project_id,
                d.status,
                d.file_name,
                COUNT(kb.id)::int AS chunk_count
            FROM knowledge_documents AS d
            LEFT JOIN knowledge_base AS kb ON kb.document_id = d.id
            WHERE d.id = $1::uuid
            GROUP BY d.id, d.project_id, d.status, d.file_name
            """,
            document_id,
        )

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Knowledge document not found: {document_id}",
        )

    return {
        "id": str(row["id"]),
        "project_id": str(row["project_id"]),
        "status": str(row["status"]),
        "file_name": str(row["file_name"]),
        "chunk_count": int(row["chunk_count"] or 0),
    }


@router.get("/documents/{document_id}/latest-report")
async def get_latest_rag_eval_report(
    document_id: str,
    current_user_id: str = Depends(get_current_user_id),
    pool: asyncpg.Pool = Depends(get_pool),
    project_repo: ProjectRepository = Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
) -> dict[str, object]:
    resolved_document_id = await _resolve_document_id(pool, document_id)
    health = await _document_health(pool, resolved_document_id)
    project_id = health["project_id"]

    await _require_project_rag_eval_access(
        project_id=project_id,
        current_user_id=current_user_id,
        project_repo=project_repo,
        user_repo=user_repo,
    )

    rag_eval_repo = RagEvalRepository(pool)
    report = await rag_eval_repo.get_latest_report(
        project_id=project_id,
        document_id=resolved_document_id,
    )

    return {
        "ok": True,
        "document": health,
        "report": report,
    }


@router.get("/documents/{document_id}/status")
async def get_rag_eval_document_status(
    document_id: str,
    current_user_id: str = Depends(get_current_user_id),
    pool: asyncpg.Pool = Depends(get_pool),
    project_repo: ProjectRepository = Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
) -> dict[str, object]:
    resolved_document_id = await _resolve_document_id(pool, document_id)
    health = await _document_health(pool, resolved_document_id)
    project_id = health["project_id"]

    await _require_project_rag_eval_access(
        project_id=project_id,
        current_user_id=current_user_id,
        project_repo=project_repo,
        user_repo=user_repo,
    )

    rag_eval_repo = RagEvalRepository(pool)
    run = await rag_eval_repo.get_latest_run_summary(
        project_id=project_id,
        document_id=resolved_document_id,
    )
    report = await rag_eval_repo.get_latest_report(
        project_id=project_id,
        document_id=resolved_document_id,
    )

    return {
        "ok": True,
        "document": health,
        "run": run,
        "report": report,
    }


@router.post("/documents/{document_id}/run-full", status_code=status.HTTP_202_ACCEPTED)
async def enqueue_full_rag_eval_for_document(
    document_id: str,
    questions_per_chunk: QuestionsPerChunkQuery = 1,
    max_questions: MaxFullQuestionsQuery = None,
    current_user_id: str = Depends(get_current_user_id),
    pool: asyncpg.Pool = Depends(get_pool),
    project_repo: ProjectRepository = Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
    queue_repo: QueueRepository = Depends(get_queue_repo),
) -> dict[str, object]:
    _require_groq_key()

    resolved_document_id = await _resolve_document_id(pool, document_id)
    health = await _document_health(pool, resolved_document_id)
    project_id = health["project_id"]

    await _require_project_rag_eval_access(
        project_id=project_id,
        current_user_id=current_user_id,
        project_repo=project_repo,
        user_repo=user_repo,
    )

    if health["status"] != "processed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Document must be processed, got status={health['status']}",
        )

    if health["chunk_count"] <= 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document has no knowledge_base chunks",
        )

    payload: dict[str, JsonValue] = {
        "project_id": project_id,
        "document_id": resolved_document_id,
        "requested_by": current_user_id,
        "mode": "full_document",
        "questions_per_chunk": questions_per_chunk,
        "max_questions": max_questions,
        "retrieval_limit": 5,
    }

    job_id = await queue_repo.enqueue(
        TASK_RUN_FULL_RAG_EVAL,
        payload,
        max_attempts=20,
    )

    return {
        "ok": True,
        "queued": True,
        "job_id": job_id,
        "document": health,
        "mode": "full_document",
        "questions_per_chunk": questions_per_chunk,
        "target_questions": int(health["chunk_count"]) * questions_per_chunk
        if max_questions is None
        else min(int(health["chunk_count"]) * questions_per_chunk, max_questions),
    }


@router.post("/documents/{document_id}/run")
async def run_rag_eval_for_document(
    document_id: str,
    mode: ModeQuery = "quick",
    max_questions: MaxQuestionsQuery = None,
    current_user_id: str = Depends(get_current_user_id),
    pool: asyncpg.Pool = Depends(get_pool),
    project_repo: ProjectRepository = Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
) -> dict[str, object]:
    _require_groq_key()
    questions_limit = _question_limit(mode, max_questions)

    resolved_document_id = await _resolve_document_id(pool, document_id)
    health = await _document_health(pool, resolved_document_id)
    project_id = health["project_id"]

    await _require_project_rag_eval_access(
        project_id=project_id,
        current_user_id=current_user_id,
        project_repo=project_repo,
        user_repo=user_repo,
    )

    if health["status"] != "processed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Document must be processed, got status={health['status']}",
        )

    if health["chunk_count"] <= 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document has no knowledge_base chunks",
        )

    knowledge_repo = KnowledgeRepository(pool)
    rag_service = RAGService(
        cast(KnowledgeSearchRepository, knowledge_repo),
        query_expander=GroqQueryExpander(),
    )
    rag_eval_repo = RagEvalRepository(pool)

    json_llm = GroqRagEvalJsonLlmAdapter(model=RAG_EVAL_GROQ_MODEL)
    dataset_generator = LlmRagEvalDatasetGenerator(
        llm=json_llm,
        model_name=RAG_EVAL_GROQ_MODEL,
    )
    answer_judge = LlmRagEvalAnswerJudge(llm=json_llm)

    runner = RagEvalRunner(
        retriever=RagServiceRagEvalRetriever(rag_service),
        answerer=ProductionRagEvalAnswerer(),
        answer_judge=answer_judge,
        retrieval_limit=5,
    )

    service = RagEvalService(
        chunk_source=rag_eval_repo,
        dataset_generator=dataset_generator,
        runner=runner,
        reporter=RagQualityReporter(),
        store=rag_eval_repo,
        report_sink=None,
    )

    run, report = await service.generate_dataset_and_run(
        project_id=project_id,
        document_id=resolved_document_id,
        max_questions=questions_limit,
    )

    return {
        "ok": True,
        "document": health,
        "mode": mode,
        "max_questions": questions_limit,
        "dataset_id": run.dataset_id,
        "run_id": run.id,
        "questions": len(run.results),
        "score": report.score,
        "readiness": report.readiness,
        "report": report.to_json(),
    }


def _queue_json_payload(raw_payload: object) -> dict[str, object]:
    import json

    if isinstance(raw_payload, dict):
        return cast(dict[str, object], raw_payload)

    if isinstance(raw_payload, str):
        decoded = json.loads(raw_payload)
        if isinstance(decoded, dict):
            return cast(dict[str, object], decoded)

    return {}


def _iso_or_none(value: object) -> str | None:
    if value is None:
        return None

    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        return str(isoformat())

    return str(value)


def _rag_eval_job_effective_status(row: asyncpg.Record) -> str:
    raw_status = str(row["status"])
    locked_at = row["locked_at"]
    error = row["error"]

    if raw_status == "pending" and locked_at is not None:
        if isinstance(error, str) and error.startswith("paused:"):
            return "paused"
        return "running_or_locked"

    return raw_status


def _rag_eval_job_percent(row: asyncpg.Record) -> float:
    effective_status = _rag_eval_job_effective_status(row)

    if effective_status in {"completed", "succeeded", "success", "failed", "cancelled"}:
        return 100.0

    if effective_status == "running_or_locked":
        return 10.0

    return 0.0


def _serialize_rag_eval_job(row: asyncpg.Record) -> dict[str, object]:
    payload = _queue_json_payload(row["payload"])
    effective_status = _rag_eval_job_effective_status(row)

    return {
        "id": str(row["id"]),
        "task_type": str(row["task_type"]),
        "status": str(row["status"]),
        "effective_status": effective_status,
        "percent": _rag_eval_job_percent(row),
        "attempts": int(row["attempts"]),
        "max_attempts": int(row["max_attempts"]),
        "locked_at": _iso_or_none(row["locked_at"]),
        "created_at": _iso_or_none(row["created_at"]),
        "updated_at": _iso_or_none(row["updated_at"]),
        "error": None if row["error"] is None else str(row["error"]),
        "payload": payload,
        "project_id": payload.get("project_id"),
        "document_id": payload.get("document_id"),
        "requested_by": payload.get("requested_by"),
        "questions_per_chunk": payload.get("questions_per_chunk"),
        "max_questions": payload.get("max_questions"),
        "retrieval_limit": payload.get("retrieval_limit"),
        "progress_kind": "queue_coarse",
        "note": (
            "Coarse queue-level progress. Exact chunk/question progress will be added "
            "by worker heartbeat in the next patch."
        ),
    }


async def _get_rag_eval_queue_job(
    *,
    pool: asyncpg.Pool,
    job_id: str,
) -> asyncpg.Record:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                id,
                task_type,
                status,
                attempts,
                max_attempts,
                locked_at,
                created_at,
                updated_at,
                error,
                payload
            FROM public.execution_queue
            WHERE id = $1::uuid
              AND task_type = $2
            """,
            job_id,
            TASK_RUN_FULL_RAG_EVAL,
        )

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"RAG eval job not found: {job_id}",
        )

    return row


async def _require_rag_eval_queue_job_access(
    *,
    pool: asyncpg.Pool,
    job_id: str,
    current_user_id: str,
    project_repo: ProjectRepository,
    user_repo: UserRepository,
) -> asyncpg.Record:
    row = await _get_rag_eval_queue_job(pool=pool, job_id=job_id)
    payload = _queue_json_payload(row["payload"])
    project_id = payload.get("project_id")

    if not isinstance(project_id, str) or not project_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="RAG eval job payload does not contain project_id",
        )

    await _require_project_rag_eval_access(
        project_id=project_id,
        current_user_id=current_user_id,
        project_repo=project_repo,
        user_repo=user_repo,
    )

    return row


@router.get("/documents/{document_id}/jobs")
async def list_rag_eval_jobs_for_document(
    document_id: str,
    current_user_id: str = Depends(get_current_user_id),
    pool: asyncpg.Pool = Depends(get_pool),
    project_repo: ProjectRepository = Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
) -> dict[str, object]:
    resolved_document_id = await _resolve_document_id(pool, document_id)
    health = await _document_health(pool, resolved_document_id)
    project_id = health["project_id"]

    await _require_project_rag_eval_access(
        project_id=project_id,
        current_user_id=current_user_id,
        project_repo=project_repo,
        user_repo=user_repo,
    )

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                id,
                task_type,
                status,
                attempts,
                max_attempts,
                locked_at,
                created_at,
                updated_at,
                error,
                payload
            FROM public.execution_queue
            WHERE task_type = $1
              AND payload::jsonb ->> 'document_id' = $2
            ORDER BY created_at DESC
            LIMIT 20
            """,
            TASK_RUN_FULL_RAG_EVAL,
            resolved_document_id,
        )

    return {
        "ok": True,
        "document": health,
        "jobs": [_serialize_rag_eval_job(row) for row in rows],
    }


@router.get("/jobs/{job_id}/progress")
async def get_rag_eval_job_progress(
    job_id: str,
    current_user_id: str = Depends(get_current_user_id),
    pool: asyncpg.Pool = Depends(get_pool),
    project_repo: ProjectRepository = Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
) -> dict[str, object]:
    row = await _require_rag_eval_queue_job_access(
        pool=pool,
        job_id=job_id,
        current_user_id=current_user_id,
        project_repo=project_repo,
        user_repo=user_repo,
    )

    return {
        "ok": True,
        "job": _serialize_rag_eval_job(row),
    }


@router.post("/jobs/{job_id}/cancel")
async def cancel_rag_eval_job(
    job_id: str,
    reason: Annotated[
        str | None,
        Query(max_length=500, description="Optional cancellation reason."),
    ] = None,
    current_user_id: str = Depends(get_current_user_id),
    pool: asyncpg.Pool = Depends(get_pool),
    project_repo: ProjectRepository = Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
) -> dict[str, object]:
    await _require_rag_eval_queue_job_access(
        pool=pool,
        job_id=job_id,
        current_user_id=current_user_id,
        project_repo=project_repo,
        user_repo=user_repo,
    )

    message = reason or "cancelled by user"

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE public.execution_queue
            SET
                status = 'failed',
                attempts = max_attempts,
                locked_at = NULL,
                error = $2,
                updated_at = now()
            WHERE id = $1::uuid
              AND task_type = $3
              AND status NOT IN ('completed', 'failed')
            RETURNING
                id,
                task_type,
                status,
                attempts,
                max_attempts,
                locked_at,
                created_at,
                updated_at,
                error,
                payload
            """,
            job_id,
            f"manually cancelled: {message}",
            TASK_RUN_FULL_RAG_EVAL,
        )

    if row is None:
        row = await _get_rag_eval_queue_job(pool=pool, job_id=job_id)

    return {
        "ok": True,
        "job": _serialize_rag_eval_job(row),
    }


@router.post("/jobs/{job_id}/pause")
async def pause_rag_eval_job(
    job_id: str,
    reason: Annotated[
        str | None,
        Query(max_length=500, description="Optional pause reason."),
    ] = None,
    current_user_id: str = Depends(get_current_user_id),
    pool: asyncpg.Pool = Depends(get_pool),
    project_repo: ProjectRepository = Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
) -> dict[str, object]:
    existing = await _require_rag_eval_queue_job_access(
        pool=pool,
        job_id=job_id,
        current_user_id=current_user_id,
        project_repo=project_repo,
        user_repo=user_repo,
    )

    if existing["locked_at"] is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Job is already locked/running. Pause is safe only before worker claim. "
                "Use cancel to stop retries; an already in-flight LLM call may still finish."
            ),
        )

    message = reason or "paused by user"

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE public.execution_queue
            SET
                locked_at = now() + interval '100 years',
                error = $2,
                updated_at = now()
            WHERE id = $1::uuid
              AND task_type = $3
              AND status = 'pending'
              AND locked_at IS NULL
            RETURNING
                id,
                task_type,
                status,
                attempts,
                max_attempts,
                locked_at,
                created_at,
                updated_at,
                error,
                payload
            """,
            job_id,
            f"paused: {message}",
            TASK_RUN_FULL_RAG_EVAL,
        )

    if row is None:
        row = await _get_rag_eval_queue_job(pool=pool, job_id=job_id)

    return {
        "ok": True,
        "job": _serialize_rag_eval_job(row),
    }


@router.post("/jobs/{job_id}/resume")
async def resume_rag_eval_job(
    job_id: str,
    current_user_id: str = Depends(get_current_user_id),
    pool: asyncpg.Pool = Depends(get_pool),
    project_repo: ProjectRepository = Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
) -> dict[str, object]:
    await _require_rag_eval_queue_job_access(
        pool=pool,
        job_id=job_id,
        current_user_id=current_user_id,
        project_repo=project_repo,
        user_repo=user_repo,
    )

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE public.execution_queue
            SET
                locked_at = NULL,
                error = NULL,
                updated_at = now()
            WHERE id = $1::uuid
              AND task_type = $2
              AND status = 'pending'
              AND error LIKE 'paused:%'
            RETURNING
                id,
                task_type,
                status,
                attempts,
                max_attempts,
                locked_at,
                created_at,
                updated_at,
                error,
                payload
            """,
            job_id,
            TASK_RUN_FULL_RAG_EVAL,
        )

    if row is None:
        row = await _get_rag_eval_queue_job(pool=pool, job_id=job_id)

    return {
        "ok": True,
        "job": _serialize_rag_eval_job(row),
    }
