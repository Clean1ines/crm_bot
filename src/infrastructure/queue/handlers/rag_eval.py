from __future__ import annotations

import os
import asyncio
import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import cast

import asyncpg
from groq import APIConnectionError, APIError, APITimeoutError, RateLimitError

from src.application.rag_eval.dataset_generator import (
    LlmRagEvalDatasetGenerator,
    MAX_CHUNKS_PER_LLM_BATCH,
)
from src.application.rag_eval.judge import LlmRagEvalAnswerJudge
from src.application.rag_eval.reporter import RagQualityReporter
from src.application.rag_eval.runner import RagEvalRunner
from src.application.rag_eval.service import RagEvalService
from src.infrastructure.config.settings import settings
from src.infrastructure.db.repositories.knowledge_repository import KnowledgeRepository
from src.infrastructure.db.repositories.rag_eval_repository import RagEvalRepository
from src.infrastructure.llm.query_expander import GroqQueryExpander
from src.infrastructure.llm.rag_contract import KnowledgeSearchRepository
from src.infrastructure.llm.rag_service import RAGService
from src.infrastructure.logging.logger import get_logger
from src.infrastructure.rag_eval.adapters import (
    GroqRagEvalJsonLlmAdapter,
    RagServiceRagEvalRetriever,
)
from src.infrastructure.queue.job_exceptions import PermanentJobError, TransientJobError
from src.interfaces.composition.rag_eval_answerer import ProductionRagEvalAnswerer

logger = get_logger(__name__)

RAG_EVAL_QUESTION_MODEL = os.getenv("RAG_EVAL_QUESTION_MODEL", "openai/gpt-oss-120b")
RAG_EVAL_JUDGE_MODEL = os.getenv("RAG_EVAL_JUDGE_MODEL", "llama-3.1-8b-instant")
RAG_EVAL_QUESTION_MAX_TOKENS = 8192
RAG_EVAL_JUDGE_MAX_TOKENS = 2048


def _coerce_int(
    value: object,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    if isinstance(value, bool):
        return default

    try:
        parsed = int(str(value).strip()) if value is not None else default
    except (TypeError, ValueError):
        parsed = default

    return max(minimum, min(maximum, parsed))


def _optional_int(value: object, *, minimum: int, maximum: int) -> int | None:
    if value is None or value == "":
        return None

    if isinstance(value, bool):
        return None

    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return None

    return max(minimum, min(maximum, parsed))


def _payload_text(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    text = str(value or "").strip()
    if not text:
        raise PermanentJobError(f"run_full_rag_eval payload missing {key}")
    return text


def _retry_after_seconds(exc: BaseException) -> float | None:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if headers is not None:
        raw_header = headers.get("retry-after") or headers.get("Retry-After")
        if raw_header:
            try:
                return max(1.0, float(str(raw_header).strip()))
            except ValueError:
                pass

    message = str(exc)
    match = re.search(r"try again in\s+([0-9]+(?:\.[0-9]+)?)s", message, re.IGNORECASE)
    if match:
        return max(1.0, float(match.group(1)))

    return None


def _transient_from_provider_error(exc: BaseException) -> TransientJobError:
    retry_after = _retry_after_seconds(exc)
    return TransientJobError(
        str(exc)[:700],
        retry_after_seconds=retry_after,
    )


RAG_EVAL_PROGRESS_PAYLOAD_KEY = "rag_eval_progress"
RAG_EVAL_CONTROL_PAYLOAD_KEY = "rag_eval_control"
RAG_EVAL_PAUSE_SLEEP_SECONDS = 3.0


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _json_mapping(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return cast(dict[str, object], value)

    if isinstance(value, str) and value.strip():
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return {}
        if isinstance(decoded, dict):
            return cast(dict[str, object], decoded)

    return {}


def _json_dumps(value: Mapping[str, object]) -> str:
    return json.dumps(dict(value), ensure_ascii=False, sort_keys=True)


async def _write_rag_eval_progress(
    *,
    db_pool: asyncpg.Pool,
    job_id: str,
    progress: Mapping[str, object],
) -> None:
    encoded = _json_dumps(progress)

    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE public.execution_queue
            SET
                payload = jsonb_set(
                    COALESCE(payload::jsonb, '{}'::jsonb),
                    $2::text[],
                    $3::jsonb,
                    true
                ),
                locked_at = CASE
                    WHEN locked_at IS NULL THEN locked_at
                    ELSE now()
                END,
                updated_at = now()
            WHERE id = $1::uuid
              AND task_type = 'run_full_rag_eval'
            """,
            job_id,
            [RAG_EVAL_PROGRESS_PAYLOAD_KEY],
            encoded,
        )

    logger.info(
        "RAG eval progress heartbeat",
        extra={
            "job_id": job_id,
            "stage": progress.get("stage"),
            "status": progress.get("status"),
            "percent": progress.get("percent"),
            "generated_questions": progress.get("generated_questions"),
            "target_questions": progress.get("target_questions"),
            "processed_batches": progress.get("processed_batches"),
            "total_batches": progress.get("total_batches"),
            "processed_questions": progress.get("processed_questions"),
            "total_questions": progress.get("total_questions"),
            "message": progress.get("message"),
        },
    )


async def _read_rag_eval_job_state(
    *,
    db_pool: asyncpg.Pool,
    job_id: str,
) -> tuple[str, str | None, dict[str, object]]:
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT status, error, payload
            FROM public.execution_queue
            WHERE id = $1::uuid
              AND task_type = 'run_full_rag_eval'
            """,
            job_id,
        )

    if row is None:
        raise PermanentJobError(f"RAG eval queue job disappeared: {job_id}")

    return (
        str(row["status"]),
        None if row["error"] is None else str(row["error"]),
        _json_mapping(row["payload"]),
    )


def _build_rag_eval_answer_progress(
    *,
    base_progress: Mapping[str, object],
    processed_questions: int,
    total_questions: int,
) -> dict[str, object]:
    safe_total = max(total_questions, 1)
    progress_ratio = min(max(processed_questions, 0) / safe_total, 1.0)
    percent = round(60.0 + (progress_ratio * 38.0), 2)

    return {
        **dict(base_progress),
        "stage": "answer_generation",
        "status": "running",
        "message": "Checking generated questions against project knowledge",
        "generated_questions": base_progress.get("target_questions"),
        "target_questions": base_progress.get("target_questions"),
        "processed_questions": processed_questions,
        "total_questions": total_questions,
        "percent": percent,
        "updated_at": _utc_now_iso(),
    }


async def _wait_if_paused_or_cancelled(
    *,
    db_pool: asyncpg.Pool,
    job_id: str,
    base_progress: Mapping[str, object],
) -> None:
    while True:
        queue_status, queue_error, payload = await _read_rag_eval_job_state(
            db_pool=db_pool,
            job_id=job_id,
        )

        control = payload.get(RAG_EVAL_CONTROL_PAYLOAD_KEY)
        control_payload = control if isinstance(control, Mapping) else {}
        action = str(control_payload.get("action") or "").strip().lower()

        if queue_status in {"failed", "cancelled"} and action != "pause":
            await _write_rag_eval_progress(
                db_pool=db_pool,
                job_id=job_id,
                progress={
                    **dict(base_progress),
                    "stage": "cancelled",
                    "status": "cancelled",
                    "message": queue_error or "RAG eval job was cancelled",
                    "updated_at": _utc_now_iso(),
                },
            )
            raise PermanentJobError(queue_error or "RAG eval job was cancelled")

        if action == "cancel":
            reason = str(control_payload.get("reason") or "cancelled by user")
            await _write_rag_eval_progress(
                db_pool=db_pool,
                job_id=job_id,
                progress={
                    **dict(base_progress),
                    "stage": "cancelled",
                    "status": "cancelled",
                    "message": reason,
                    "updated_at": _utc_now_iso(),
                },
            )
            raise PermanentJobError(reason)

        if action != "pause":
            return

        reason = str(control_payload.get("reason") or "paused by user")
        await _write_rag_eval_progress(
            db_pool=db_pool,
            job_id=job_id,
            progress={
                **dict(base_progress),
                "stage": "paused",
                "status": "paused",
                "message": reason,
                "updated_at": _utc_now_iso(),
            },
        )
        await asyncio.sleep(RAG_EVAL_PAUSE_SLEEP_SECONDS)


async def handle_run_full_rag_eval(
    job: Mapping[str, object],
    *,
    db_pool: asyncpg.Pool,
) -> None:
    payload = job.get("payload") or {}
    if not isinstance(payload, Mapping):
        raise PermanentJobError("run_full_rag_eval payload must be an object")

    if not settings.GROQ_API_KEY:
        raise PermanentJobError("GROQ_API_KEY is not configured")

    try:
        await _run_full_document_rag_eval(
            job_id=str(job.get("id") or ""),
            payload=payload,
            db_pool=db_pool,
        )
    except (APIConnectionError, APITimeoutError, RateLimitError) as exc:
        logger.warning(
            "Full-document RAG eval provider transient failure",
            extra={
                "job_id": job.get("id"),
                "error_type": type(exc).__name__,
                "error": str(exc)[:300],
            },
        )
        raise _transient_from_provider_error(exc) from exc
    except APIError as exc:
        status_code = getattr(exc, "status_code", None)
        if status_code == 429 or (isinstance(status_code, int) and status_code >= 500):
            logger.warning(
                "Full-document RAG eval provider API retryable failure",
                extra={
                    "job_id": job.get("id"),
                    "status_code": status_code,
                    "error": str(exc)[:300],
                },
            )
            raise _transient_from_provider_error(exc) from exc
        raise PermanentJobError(str(exc)[:700]) from exc


async def _run_full_document_rag_eval(
    *,
    job_id: str,
    payload: Mapping[str, object],
    db_pool: asyncpg.Pool,
) -> None:
    project_id = _payload_text(payload, "project_id")
    document_id = _payload_text(payload, "document_id")
    requested_by = str(payload.get("requested_by") or "").strip() or None

    rag_eval_repo = RagEvalRepository(db_pool)
    chunks = await rag_eval_repo.load_document_chunks(
        project_id=project_id,
        document_id=document_id,
    )

    if not chunks:
        raise PermanentJobError("Document has no processed knowledge chunks")

    total_batches = max(
        1,
        (len(chunks) + MAX_CHUNKS_PER_LLM_BATCH - 1) // MAX_CHUNKS_PER_LLM_BATCH,
    )
    full_document_target = total_batches

    retrieval_limit = _coerce_int(
        payload.get("retrieval_limit"),
        default=5,
        minimum=1,
        maximum=20,
    )

    question_max_tokens = _coerce_int(
        payload.get("question_llm_max_tokens"),
        default=RAG_EVAL_QUESTION_MAX_TOKENS,
        minimum=2048,
        maximum=8192,
    )
    judge_max_tokens = _coerce_int(
        payload.get("judge_llm_max_tokens"),
        default=RAG_EVAL_JUDGE_MAX_TOKENS,
        minimum=512,
        maximum=4096,
    )

    knowledge_repo = KnowledgeRepository(db_pool)
    rag_service = RAGService(
        cast(KnowledgeSearchRepository, knowledge_repo),
        query_expander=GroqQueryExpander(),
    )

    question_llm = GroqRagEvalJsonLlmAdapter(
        model=RAG_EVAL_QUESTION_MODEL,
        max_tokens=question_max_tokens,
    )
    judge_llm = GroqRagEvalJsonLlmAdapter(
        model=RAG_EVAL_JUDGE_MODEL,
        max_tokens=judge_max_tokens,
    )
    dataset_generator = LlmRagEvalDatasetGenerator(
        llm=question_llm,
        model_name=RAG_EVAL_QUESTION_MODEL,
    )
    answer_judge = LlmRagEvalAnswerJudge(llm=judge_llm)

    runner = RagEvalRunner(
        retriever=RagServiceRagEvalRetriever(rag_service),
        answerer=ProductionRagEvalAnswerer(),
        answer_judge=answer_judge,
        retrieval_limit=retrieval_limit,
    )

    service = RagEvalService(
        chunk_source=rag_eval_repo,
        dataset_generator=dataset_generator,
        runner=runner,
        reporter=RagQualityReporter(),
        store=rag_eval_repo,
        report_sink=None,
    )

    source_chunk_count = len(chunks)
    total_batches = max(
        1,
        (len(chunks) + MAX_CHUNKS_PER_LLM_BATCH - 1) // MAX_CHUNKS_PER_LLM_BATCH,
    )

    base_progress: dict[str, object] = {
        "project_id": project_id,
        "document_id": document_id,
        "requested_by": requested_by,
        "source_chunk_count": source_chunk_count,
        "target_questions": full_document_target,
        "retrieval_limit": retrieval_limit,
        "total_batches": total_batches,
        "updated_at": _utc_now_iso(),
    }

    current_control_progress: dict[str, object] = {
        **base_progress,
        "stage": "started",
        "status": "running",
        "message": "Full-document RAG eval worker started",
        "generated_questions": 0,
        "target_questions": full_document_target,
        "processed_batches": 0,
        "total_batches": total_batches,
        "percent": 0.0,
        "updated_at": _utc_now_iso(),
    }

    async def _on_dataset_progress(
        generated_questions: int,
        target_questions: int,
        processed_batches: int,
    ) -> None:
        nonlocal current_control_progress
        safe_target = max(target_questions, 1)
        safe_batches = max(total_batches, 1)
        batch_percent = min(max(processed_batches, 0) / safe_batches, 1.0)
        question_percent = min(max(generated_questions, 0) / safe_target, 1.0)
        percent = round(max(batch_percent, question_percent) * 60.0, 2)

        progress = {
            **base_progress,
            "stage": "dataset_generation",
            "status": "running",
            "message": "Generating RAG eval questions from document chunks",
            "generated_questions": generated_questions,
            "target_questions": target_questions,
            "processed_batches": processed_batches,
            "total_batches": total_batches,
            "percent": percent,
            "updated_at": _utc_now_iso(),
        }
        current_control_progress = progress
        await _write_rag_eval_progress(
            db_pool=db_pool,
            job_id=job_id,
            progress=progress,
        )

    async def _on_run_progress(
        processed_questions: int,
        total_questions: int,
    ) -> None:
        nonlocal current_control_progress
        progress = _build_rag_eval_answer_progress(
            base_progress=base_progress,
            processed_questions=processed_questions,
            total_questions=total_questions,
        )
        current_control_progress = progress
        await _write_rag_eval_progress(
            db_pool=db_pool,
            job_id=job_id,
            progress=progress,
        )

    async def _control_callback() -> None:
        await _wait_if_paused_or_cancelled(
            db_pool=db_pool,
            job_id=job_id,
            base_progress=current_control_progress,
        )

    await _write_rag_eval_progress(
        db_pool=db_pool,
        job_id=job_id,
        progress={
            **base_progress,
            "stage": "started",
            "status": "running",
            "message": "Full-document RAG eval worker started",
            "generated_questions": 0,
            "target_questions": full_document_target,
            "processed_batches": 0,
            "total_batches": total_batches,
            "percent": 0.0,
            "updated_at": _utc_now_iso(),
        },
    )

    try:
        run, report = await service.generate_dataset_and_run(
            project_id=project_id,
            document_id=document_id,
            progress_callback=_on_dataset_progress,
            control_callback=_control_callback,
        )
    except Exception as exc:
        await _write_rag_eval_progress(
            db_pool=db_pool,
            job_id=job_id,
            progress={
                **base_progress,
                "stage": "failed",
                "status": "failed",
                "message": str(exc)[:500],
                "percent": 100.0,
                "updated_at": _utc_now_iso(),
            },
        )
        raise

    await _write_rag_eval_progress(
        db_pool=db_pool,
        job_id=job_id,
        progress={
            **base_progress,
            "stage": "completed",
            "status": "completed",
            "message": "Full-document RAG eval completed",
            "generated_questions": len(run.results),
            "target_questions": full_document_target,
            "processed_questions": len(run.results),
            "total_questions": len(run.results),
            "processed_batches": total_batches,
            "total_batches": total_batches,
            "percent": 100.0,
            "updated_at": _utc_now_iso(),
        },
    )

    logger.info(
        "Full-document RAG eval completed",
        extra={
            "project_id": project_id,
            "document_id": document_id,
            "run_id": run.id,
            "dataset_id": run.dataset_id,
            "questions": len(run.results),
            "score": report.score,
            "readiness": report.readiness,
        },
    )
