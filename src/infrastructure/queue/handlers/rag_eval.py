from __future__ import annotations

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

RAG_EVAL_GROQ_MODEL = "llama-3.1-8b-instant"


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


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _coerce_payload_mapping(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return dict(value)

    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return {}

        if isinstance(decoded, dict):
            return dict(decoded)

    return {}


async def _write_rag_eval_job_progress(
    *,
    db_pool: asyncpg.Pool,
    job_id: str,
    stage: str,
    status: str,
    message: str,
    target_questions: int,
    generated_questions: int,
    processed_batches: int,
    total_batches: int,
    extra: Mapping[str, object] | None = None,
) -> None:
    safe_target = max(target_questions, 1)
    percent = min(
        100.0,
        round((max(generated_questions, 0) / safe_target) * 100.0, 2),
    )

    progress: dict[str, object] = {
        "stage": stage,
        "status": status,
        "message": message,
        "target_questions": target_questions,
        "generated_questions": generated_questions,
        "processed_batches": processed_batches,
        "total_batches": max(total_batches, processed_batches, 1),
        "percent": percent,
        "updated_at": _utc_now_iso(),
    }

    if extra:
        progress.update(extra)

    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE execution_queue
            SET
                payload = COALESCE(payload, '{}'::jsonb)
                    || jsonb_build_object($2::text, $3::jsonb),
                updated_at = NOW()
            WHERE id = $1::uuid
            """,
            job_id,
            RAG_EVAL_PROGRESS_PAYLOAD_KEY,
            json.dumps(progress, ensure_ascii=False),
        )


async def _read_rag_eval_job_state(
    *,
    db_pool: asyncpg.Pool,
    job_id: str,
) -> tuple[str, dict[str, object]]:
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT status, payload
            FROM execution_queue
            WHERE id = $1::uuid
            """,
            job_id,
        )

    if row is None:
        return "missing", {}

    return str(row["status"]), _coerce_payload_mapping(row["payload"])


def _control_action(payload: Mapping[str, object]) -> str:
    control = payload.get(RAG_EVAL_CONTROL_PAYLOAD_KEY)
    if not isinstance(control, Mapping):
        return ""

    raw_action = control.get("action")
    if not isinstance(raw_action, str):
        return ""

    return raw_action.strip().lower()


async def _wait_if_rag_eval_job_paused_or_cancelled(
    *,
    db_pool: asyncpg.Pool,
    job_id: str,
    target_questions: int,
    generated_questions: int,
    processed_batches: int,
    total_batches: int,
) -> None:
    while True:
        queue_status, payload = await _read_rag_eval_job_state(
            db_pool=db_pool,
            job_id=job_id,
        )
        action = _control_action(payload)

        if queue_status in {"missing", "failed", "cancelled"} or action == "cancel":
            await _write_rag_eval_job_progress(
                db_pool=db_pool,
                job_id=job_id,
                stage="cancelled",
                status="cancelled",
                message="RAG eval cancelled before next LLM batch",
                target_questions=target_questions,
                generated_questions=generated_questions,
                processed_batches=processed_batches,
                total_batches=total_batches,
                extra={"queue_status": queue_status, "control_action": action},
            )
            raise PermanentJobError("RAG eval job cancelled manually")

        if queue_status == "paused" or action == "pause":
            await _write_rag_eval_job_progress(
                db_pool=db_pool,
                job_id=job_id,
                stage="paused",
                status="paused",
                message="RAG eval paused; waiting for resume",
                target_questions=target_questions,
                generated_questions=generated_questions,
                processed_batches=processed_batches,
                total_batches=total_batches,
                extra={"queue_status": queue_status, "control_action": action},
            )
            await asyncio.sleep(5.0)
            continue

        return


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

    questions_per_chunk = _coerce_int(
        payload.get("questions_per_chunk"),
        default=1,
        minimum=1,
        maximum=5,
    )
    full_document_target = max(len(chunks) * questions_per_chunk, len(chunks))

    explicit_max_questions = _optional_int(
        payload.get("max_questions"),
        minimum=1,
        maximum=50000,
    )
    if explicit_max_questions is not None:
        full_document_target = min(full_document_target, explicit_max_questions)

    source_chunk_count = len(chunks)
    total_batches = max(
        (source_chunk_count + MAX_CHUNKS_PER_LLM_BATCH - 1) // MAX_CHUNKS_PER_LLM_BATCH,
        1,
    )

    retrieval_limit = _coerce_int(
        payload.get("retrieval_limit"),
        default=5,
        minimum=1,
        maximum=20,
    )
    llm_max_tokens = _coerce_int(
        payload.get("llm_max_tokens"),
        default=2048,
        minimum=512,
        maximum=4096,
    )

    knowledge_repo = KnowledgeRepository(db_pool)
    rag_service = RAGService(
        cast(KnowledgeSearchRepository, knowledge_repo),
        query_expander=GroqQueryExpander(),
    )

    json_llm = GroqRagEvalJsonLlmAdapter(
        model=RAG_EVAL_GROQ_MODEL, max_tokens=llm_max_tokens
    )
    dataset_generator = LlmRagEvalDatasetGenerator(
        llm=json_llm,
        model_name=RAG_EVAL_GROQ_MODEL,
    )
    answer_judge = LlmRagEvalAnswerJudge(llm=json_llm)

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

    logger.info(
        "Starting full-document RAG eval",
        extra={
            "project_id": project_id,
            "document_id": document_id,
            "requested_by": requested_by,
            "source_chunk_count": source_chunk_count,
            "questions_per_chunk": questions_per_chunk,
            "target_questions": full_document_target,
            "retrieval_limit": retrieval_limit,
        },
    )

    progress_state: dict[str, int] = {
        "generated_questions": 0,
        "processed_batches": 0,
    }

    await _write_rag_eval_job_progress(
        db_pool=db_pool,
        job_id=job_id,
        stage="dataset_generation",
        status="running",
        message="Starting RAG eval dataset generation",
        target_questions=full_document_target,
        generated_questions=0,
        processed_batches=0,
        total_batches=total_batches,
        extra={
            "project_id": project_id,
            "document_id": document_id,
            "source_chunk_count": source_chunk_count,
            "questions_per_chunk": questions_per_chunk,
            "retrieval_limit": retrieval_limit,
        },
    )

    async def _on_dataset_progress(
        generated_questions: int,
        target_questions: int,
        batch_index: int,
    ) -> None:
        progress_state["generated_questions"] = generated_questions
        progress_state["processed_batches"] = batch_index

        await _write_rag_eval_job_progress(
            db_pool=db_pool,
            job_id=job_id,
            stage="dataset_generation",
            status="running",
            message="Generating RAG eval questions from document chunks",
            target_questions=target_questions,
            generated_questions=generated_questions,
            processed_batches=batch_index,
            total_batches=total_batches,
            extra={
                "project_id": project_id,
                "document_id": document_id,
                "source_chunk_count": source_chunk_count,
                "questions_per_chunk": questions_per_chunk,
                "retrieval_limit": retrieval_limit,
            },
        )

    async def _control_callback() -> None:
        await _wait_if_rag_eval_job_paused_or_cancelled(
            db_pool=db_pool,
            job_id=job_id,
            target_questions=full_document_target,
            generated_questions=progress_state["generated_questions"],
            processed_batches=progress_state["processed_batches"],
            total_batches=total_batches,
        )

    run, report = await service.generate_dataset_and_run(
        project_id=project_id,
        document_id=document_id,
        max_questions=full_document_target,
        progress_callback=_on_dataset_progress,
        control_callback=_control_callback,
    )

    await _write_rag_eval_job_progress(
        db_pool=db_pool,
        job_id=job_id,
        stage="completed",
        status="completed",
        message="Full-document RAG eval completed",
        target_questions=full_document_target,
        generated_questions=len(run.results),
        processed_batches=total_batches,
        total_batches=total_batches,
        extra={
            "project_id": project_id,
            "document_id": document_id,
            "run_id": run.id,
            "dataset_id": run.dataset_id,
            "score": report.score,
            "readiness": report.readiness,
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
