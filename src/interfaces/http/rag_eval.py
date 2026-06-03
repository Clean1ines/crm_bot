from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Annotated, Literal, TypedDict, cast

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from src.application.rag_eval.ports import RagEvalRetrieverPort
from src.application.rag_eval.review_service import RagEvalReviewService
from src.application.services.knowledge_edit_action_service import (
    KnowledgeEditActionExecutionResult,
    KnowledgeEditActionService,
)
from src.domain.project_plane.json_types import JsonValue
from src.domain.project_plane.rag_eval_retrieval import (
    RagEvalRetrievalMode,
    normalize_rag_eval_retrieval_mode,
    rag_eval_retrieval_metadata,
    resolve_rag_eval_retrieval_policy,
)
from src.infrastructure.db.repositories.project import ProjectRepository
from src.infrastructure.db.repositories.queue_repository import QueueRepository
from src.infrastructure.db.repositories.rag_eval_repository import RagEvalRepository
from src.infrastructure.db.repositories.user_repository import UserRepository
from src.infrastructure.queue.job_types import TASK_RUN_FULL_RAG_EVAL
from src.infrastructure.llm.groq_keyring import has_configured_groq_api_key
from src.interfaces.http.dependencies import (
    get_current_user_id,
    get_pool,
    get_queue_repo,
    get_project_repo,
    get_user_repository,
)


router = APIRouter(prefix="/api/rag-eval", tags=["rag-eval"])


PROJECT_RAG_EVAL_ROLES = ["owner", "admin"]
RAG_EVAL_QUESTION_MODEL = os.getenv("RAG_EVAL_QUESTION_MODEL", "llama-3.1-8b-instant")
RAG_EVAL_QUESTION_FALLBACK_MODEL = os.getenv(
    "RAG_EVAL_QUESTION_FALLBACK_MODEL",
    "meta-llama/llama-4-scout-17b-16e-instruct",
)
RAG_EVAL_JUDGE_MODEL = os.getenv("RAG_EVAL_JUDGE_MODEL", "llama-3.1-8b-instant")
RAG_EVAL_QUESTION_MAX_TOKENS = 6144
RAG_EVAL_JUDGE_MAX_TOKENS = 2048
RAG_EVAL_PROGRESS_PAYLOAD_KEY = "rag_eval_progress"
RAG_EVAL_CONTROL_PAYLOAD_KEY = "rag_eval_control"

RagEvalModeValue = Literal["retrieval_eval", "answer_quality_eval"]
RagEvalRetrievalModeValue = Literal["production_equivalent", "vector_debug"]

ModeQuery = Annotated[
    str,
    Query(
        description=(
            "RAG eval mode. retrieval_eval is deterministic retrieval coverage; "
            "answer_quality_eval additionally runs production answer generation and LLM judging."
        ),
        pattern="^(quick|standard|deep|paranoid|retrieval_eval|answer_quality_eval)$",
    ),
]


RetrievalModeQuery = Annotated[
    str,
    Query(
        description=(
            "RAG eval retrieval mode. production_equivalent mirrors production "
            "runtime retrieval; vector_debug checks vector-only embedding retrieval."
        ),
        pattern="^(production_equivalent|vector_debug|embedding_debug)$",
    ),
]


def _rag_eval_mode_from_query(mode: str) -> RagEvalModeValue:
    normalized = mode.strip().lower()
    if normalized == "answer_quality_eval":
        return "answer_quality_eval"
    return "retrieval_eval"


class RagEvalQuestionReviewRequest(BaseModel):
    status: Literal["accepted", "rejected"]
    reason: str = Field(default="", max_length=1000)


class RagEvalQuestionEditRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)


class RagEvalRunRequest(BaseModel):
    retrieval_mode: RagEvalRetrievalModeValue = Field(
        default=RagEvalRetrievalMode.PRODUCTION_EQUIVALENT.value
    )


class DocumentHealth(TypedDict):
    id: str
    project_id: str
    status: str
    file_name: str
    entry_count: int


class KnowledgeEditActionExecutionSummary(TypedDict):
    ok: bool
    source_result_id: str
    project_id: str
    document_id: str
    total_actions: int
    applied_actions: int
    rejected_actions: int
    failed_actions: int
    skipped_actions: int
    queued_rerun_job_ids: list[str]


def _knowledge_edit_action_execution_summary(
    result: KnowledgeEditActionExecutionResult,
) -> KnowledgeEditActionExecutionSummary:
    return {
        "ok": True,
        "source_result_id": result.source_result_id,
        "project_id": result.project_id,
        "document_id": result.document_id,
        "total_actions": result.total_actions,
        "applied_actions": result.applied_actions,
        "rejected_actions": result.rejected_actions,
        "failed_actions": result.failed_actions,
        "skipped_actions": result.skipped_actions,
        "queued_rerun_job_ids": list(result.queued_rerun_job_ids),
    }


def _require_groq_key() -> None:
    if not has_configured_groq_api_key():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No Groq API keys are configured",
        )


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
                  FROM knowledge_retrieval_surface AS rs
                  WHERE rs.document_id = d.id
              )
            ORDER BY d.created_at DESC, d.id DESC
            LIMIT 1
            """
        )

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No processed knowledge document with entries found",
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
                COUNT(rs.id)::int AS entry_count
            FROM knowledge_documents AS d
            LEFT JOIN knowledge_retrieval_surface AS rs ON rs.document_id = d.id
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
        "entry_count": int(row["entry_count"] or 0),
    }


async def _review_project_id(payload: Mapping[str, object] | None) -> str:
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="RAG eval review not found",
        )
    project_id = str(payload.get("project_id") or "").strip()
    if not project_id:
        run = payload.get("run")
        if isinstance(run, dict):
            project_id = str(run.get("project_id") or "").strip()
    if not project_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="RAG eval review is missing project_id",
        )
    return project_id


@router.get("/runs/{run_id}/review")
async def get_rag_eval_run_review(
    run_id: str,
    current_user_id: str = Depends(get_current_user_id),
    pool: asyncpg.Pool = Depends(get_pool),
    project_repo: ProjectRepository = Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
) -> dict[str, object]:
    rag_eval_repo = RagEvalRepository(pool)
    run = await rag_eval_repo.get_run_summary(run_id=run_id)
    project_id = await _review_project_id(run)

    await _require_project_rag_eval_access(
        project_id=project_id,
        current_user_id=current_user_id,
        project_repo=project_repo,
        user_repo=user_repo,
    )

    review = await RagEvalReviewService(rag_eval_repo).build_run_review(run_id=run_id)
    return {"ok": True, "review": review}


@router.get("/documents/{document_id}/latest-review")
async def get_latest_rag_eval_review(
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

    review = await RagEvalReviewService(RagEvalRepository(pool)).build_latest_review(
        project_id=project_id,
        document_id=resolved_document_id,
    )
    return {"ok": True, "document": health, "review": review}


async def _question_project_id(pool: asyncpg.Pool, question_id: str) -> str:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT project_id
            FROM rag_eval_questions
            WHERE id = $1
            """,
            question_id,
        )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"RAG eval question not found: {question_id}",
        )
    return str(row["project_id"])


@router.post("/questions/{question_id}/review")
async def review_rag_eval_question(
    question_id: str,
    request: RagEvalQuestionReviewRequest,
    current_user_id: str = Depends(get_current_user_id),
    pool: asyncpg.Pool = Depends(get_pool),
    project_repo: ProjectRepository = Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
) -> dict[str, object]:
    project_id = await _question_project_id(pool, question_id)
    await _require_project_rag_eval_access(
        project_id=project_id,
        current_user_id=current_user_id,
        project_repo=project_repo,
        user_repo=user_repo,
    )

    review = await RagEvalReviewService(RagEvalRepository(pool)).review_question(
        question_id=question_id,
        status=request.status,
        reason=request.reason,
        reviewed_by=current_user_id,
    )
    if review is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"RAG eval question result not found: {question_id}",
        )
    return {"ok": True, "review": review}


@router.patch("/questions/{question_id}")
async def edit_rag_eval_question(
    question_id: str,
    request: RagEvalQuestionEditRequest,
    current_user_id: str = Depends(get_current_user_id),
    pool: asyncpg.Pool = Depends(get_pool),
    project_repo: ProjectRepository = Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
) -> dict[str, object]:
    project_id = await _question_project_id(pool, question_id)
    await _require_project_rag_eval_access(
        project_id=project_id,
        current_user_id=current_user_id,
        project_repo=project_repo,
        user_repo=user_repo,
    )

    review = await RagEvalReviewService(RagEvalRepository(pool)).edit_question(
        question_id=question_id,
        question=request.question,
        reviewed_by=current_user_id,
    )
    if review is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"RAG eval question result not found: {question_id}",
        )
    return {"ok": True, "review": review}


@router.post("/runs/{run_id}/apply-accepted")
async def apply_accepted_rag_eval_questions(
    run_id: str,
    current_user_id: str = Depends(get_current_user_id),
    pool: asyncpg.Pool = Depends(get_pool),
    project_repo: ProjectRepository = Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
    queue_repo: QueueRepository = Depends(get_queue_repo),
) -> dict[str, object]:
    rag_eval_repo = RagEvalRepository(pool)
    run = await rag_eval_repo.get_run_summary(run_id=run_id)
    project_id = await _review_project_id(run)

    await _require_project_rag_eval_access(
        project_id=project_id,
        current_user_id=current_user_id,
        project_repo=project_repo,
        user_repo=user_repo,
    )

    from src.infrastructure.db.workbench_runtime_retrieval_repository import (
        WorkbenchRuntimeRetrievalRepository,
    )

    try:
        summary = await RagEvalReviewService(
            rag_eval_repo,
            knowledge_repo=WorkbenchRuntimeRetrievalRepository(pool),
            queue_repo=queue_repo,
            rerun_eval_task_type=TASK_RUN_FULL_RAG_EVAL,
        ).apply_accepted_questions(
            run_id=run_id,
            actor_user_id=current_user_id,
        )
    except ValueError as exc:
        detail = str(exc)
        if "not found" in detail.lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=detail,
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
        ) from exc

    return dict(summary)


@router.post("/results/{result_id}/actions/execute")
async def execute_rag_eval_result_actions(
    result_id: str,
    current_user_id: str = Depends(get_current_user_id),
    pool: asyncpg.Pool = Depends(get_pool),
    project_repo: ProjectRepository = Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
    queue_repo: QueueRepository = Depends(get_queue_repo),
) -> KnowledgeEditActionExecutionSummary:
    action_source = RagEvalRepository(pool)
    source_payload = await action_source.load_result_action_source(result_id)
    if source_payload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"RAG eval result not found: {result_id}",
        )

    project_id = str(source_payload.get("project_id") or "").strip()
    if not project_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="RAG eval result action source is missing project_id",
        )

    await _require_project_rag_eval_access(
        project_id=project_id,
        current_user_id=current_user_id,
        project_repo=project_repo,
        user_repo=user_repo,
    )

    from src.infrastructure.db.workbench_runtime_retrieval_repository import (
        WorkbenchRuntimeRetrievalRepository,
    )

    service = KnowledgeEditActionService(
        action_source=action_source,
        knowledge_repo=WorkbenchRuntimeRetrievalRepository(pool),
        queue_repo=queue_repo,
    )

    try:
        result = await service.execute_result_actions(
            result_id=result_id,
            actor_user_id=current_user_id,
        )
    except ValueError as exc:
        detail = str(exc)
        if "not found" in detail.lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=detail,
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
        ) from exc

    return _knowledge_edit_action_execution_summary(result)


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
    request: RagEvalRunRequest | None = None,
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

    if health["entry_count"] <= 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document has no retrieval surface entries",
        )

    retrieval_mode = normalize_rag_eval_retrieval_mode(
        request.retrieval_mode if request is not None else None
    )

    payload: dict[str, JsonValue] = {
        "project_id": project_id,
        "document_id": resolved_document_id,
        "requested_by": current_user_id,
        "mode": "full_document",
        "eval_mode": "retrieval_eval",
        "retrieval_mode": retrieval_mode.value,
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
        "eval_mode": "retrieval_eval",
        "retrieval_mode": retrieval_mode.value,
    }


@router.post("/documents/{document_id}/run")
async def run_rag_eval_for_document(
    document_id: str,
    mode: ModeQuery = "retrieval_eval",
    retrieval_mode: RetrievalModeQuery = RagEvalRetrievalMode.PRODUCTION_EQUIVALENT.value,
    current_user_id: str = Depends(get_current_user_id),
    pool: asyncpg.Pool = Depends(get_pool),
    project_repo: ProjectRepository = Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
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

    if health["entry_count"] <= 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document has no retrieval surface entries",
        )

    eval_mode = _rag_eval_mode_from_query(mode)
    retrieval_policy = resolve_rag_eval_retrieval_policy(
        normalize_rag_eval_retrieval_mode(retrieval_mode)
    )
    retrieval_metadata = rag_eval_retrieval_metadata(retrieval_policy)

    # Lazy imports keep plain FastAPI app import light.
    from src.application.rag_eval.dataset_generator import LlmRagEvalDatasetGenerator
    from src.application.rag_eval.reporter import RagQualityReporter
    from src.application.rag_eval.runner import RagEvalRunner
    from src.application.rag_eval.service import RagEvalService
    from src.infrastructure.db.workbench_runtime_retrieval_repository import (
        WorkbenchRuntimeRetrievalRepository,
    )
    from src.infrastructure.llm.query_expander import GroqQueryExpander
    from src.application.ports.knowledge.runtime_search import (
        KnowledgeRuntimeRetrievalPort,
    )
    from src.infrastructure.llm.rag_service import RAGService
    from src.infrastructure.rag_eval.adapters import (
        GroqRagEvalJsonLlmAdapter,
        RagServiceRagEvalRetriever,
        VectorOnlyRagEvalRetriever,
    )

    runtime_retrieval = WorkbenchRuntimeRetrievalRepository(pool)
    if retrieval_policy.mode == RagEvalRetrievalMode.VECTOR_DEBUG:
        retriever: RagEvalRetrieverPort = VectorOnlyRagEvalRetriever(
            cast(KnowledgeRuntimeRetrievalPort, runtime_retrieval)
        )
    else:
        rag_service = RAGService(
            cast(KnowledgeRuntimeRetrievalPort, runtime_retrieval),
            query_expander=GroqQueryExpander(),
        )
        retriever = RagServiceRagEvalRetriever(rag_service)
    rag_eval_repo = RagEvalRepository(pool)

    question_llm = GroqRagEvalJsonLlmAdapter(
        model=RAG_EVAL_QUESTION_MODEL,
        fallback_model=RAG_EVAL_QUESTION_FALLBACK_MODEL,
        max_tokens=RAG_EVAL_QUESTION_MAX_TOKENS,
    )
    dataset_generator = LlmRagEvalDatasetGenerator(
        llm=question_llm,
        model_name=RAG_EVAL_QUESTION_MODEL,
    )

    if eval_mode == "answer_quality_eval":
        from src.application.rag_eval.judge import LlmRagEvalAnswerJudge
        from src.interfaces.composition.rag_eval_answerer import (
            ProductionRagEvalAnswerer,
        )

        judge_llm = GroqRagEvalJsonLlmAdapter(
            model=RAG_EVAL_JUDGE_MODEL,
            max_tokens=RAG_EVAL_JUDGE_MAX_TOKENS,
        )
        runner = RagEvalRunner(
            retriever=retriever,
            answerer=ProductionRagEvalAnswerer(),
            answer_judge=LlmRagEvalAnswerJudge(llm=judge_llm),
            mode=eval_mode,
            retrieval_limit=5,
            retrieval_metadata=retrieval_metadata,
        )
    else:
        runner = RagEvalRunner(
            retriever=retriever,
            mode=eval_mode,
            retrieval_limit=5,
            retrieval_metadata=retrieval_metadata,
        )

    service = RagEvalService(
        entry_source=rag_eval_repo,
        dataset_generator=dataset_generator,
        runner=runner,
        reporter=RagQualityReporter(),
        store=rag_eval_repo,
        report_sink=None,
    )

    run, report = await service.generate_dataset_and_run(
        project_id=project_id,
        document_id=resolved_document_id,
    )

    return {
        "ok": True,
        "document": health,
        "mode": eval_mode,
        "retrieval_mode": retrieval_policy.mode.value,
        "retrieval_path": retrieval_policy.retrieval_path,
        "query_expansion_enabled": retrieval_policy.query_expansion_enabled,
        "runtime_equivalent": retrieval_policy.runtime_equivalent,
        "diagnostic": retrieval_policy.diagnostic,
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
    error_text = error if isinstance(error, str) else ""
    payload = _queue_json_payload(row["payload"])

    control = payload.get(RAG_EVAL_CONTROL_PAYLOAD_KEY)
    if isinstance(control, dict):
        action = str(control.get("action") or "").strip().lower()
        if action == "cancel":
            return "cancelled"
        if action == "pause" and raw_status not in {"completed", "done", "failed"}:
            return "paused"

    if raw_status == "failed":
        if "cancel" in error_text.lower():
            return "cancelled"
        return "failed"

    if raw_status in {"completed", "done", "succeeded", "success"}:
        return "completed"

    progress = payload.get(RAG_EVAL_PROGRESS_PAYLOAD_KEY)
    if isinstance(progress, dict):
        progress_status = str(progress.get("status") or "").strip()
        if progress_status:
            return progress_status

    if raw_status == "pending" and locked_at is not None:
        if error_text.startswith("paused:"):
            return "paused"
        return "running"

    return raw_status


def _rag_eval_job_percent(row: asyncpg.Record) -> float:
    effective_status = _rag_eval_job_effective_status(row)

    if effective_status in {
        "completed",
        "done",
        "succeeded",
        "success",
        "failed",
        "cancelled",
    }:
        return 100.0

    payload = _queue_json_payload(row["payload"])
    progress = payload.get(RAG_EVAL_PROGRESS_PAYLOAD_KEY)

    if isinstance(progress, dict):
        raw_percent = progress.get("percent")
        if isinstance(raw_percent, int | float):
            return max(0.0, min(100.0, float(raw_percent)))

    if effective_status == "running":
        return 1.0

    return 0.0


def _serialize_rag_eval_job(row: asyncpg.Record) -> dict[str, object]:
    payload = _queue_json_payload(row["payload"])
    effective_status = _rag_eval_job_effective_status(row)
    progress = payload.get(RAG_EVAL_PROGRESS_PAYLOAD_KEY)
    safe_progress = progress if isinstance(progress, dict) else None

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
        "progress": safe_progress,
        "project_id": payload.get("project_id"),
        "document_id": payload.get("document_id"),
        "requested_by": payload.get("requested_by"),
        "retrieval_limit": payload.get("retrieval_limit"),
        "retrieval_mode": payload.get("retrieval_mode"),
        "retrieval_path": (
            safe_progress.get("retrieval_path")
            if safe_progress
            else payload.get("retrieval_path")
        ),
        "progress_kind": "worker_payload_heartbeat"
        if safe_progress
        else "queue_coarse",
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
                payload = jsonb_set(
                    COALESCE(payload::jsonb, '{}'::jsonb),
                    ARRAY['rag_eval_control'],
                    jsonb_build_object(
                        'action', 'cancel',
                        'reason', $2::text,
                        'requested_at', now()::text
                    ),
                    true
                ),
                error = $2,
                updated_at = now()
            WHERE id = $1::uuid
              AND task_type = $3
              AND status NOT IN ('completed', 'done', 'failed')
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
    await _require_rag_eval_queue_job_access(
        pool=pool,
        job_id=job_id,
        current_user_id=current_user_id,
        project_repo=project_repo,
        user_repo=user_repo,
    )

    message = reason or "paused by user"

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE public.execution_queue
            SET
                payload = jsonb_set(
                    COALESCE(payload::jsonb, '{}'::jsonb),
                    ARRAY['rag_eval_control'],
                    jsonb_build_object(
                        'action', 'pause',
                        'reason', $2::text,
                        'requested_at', now()::text
                    ),
                    true
                ),
                error = $2,
                updated_at = now()
            WHERE id = $1::uuid
              AND task_type = $3
              AND status NOT IN ('completed', 'done', 'failed')
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
                payload = COALESCE(payload::jsonb, '{}'::jsonb) - 'rag_eval_control',
                error = NULL,
                updated_at = now()
            WHERE id = $1::uuid
              AND task_type = $2
              AND status NOT IN ('completed', 'done', 'failed')
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
