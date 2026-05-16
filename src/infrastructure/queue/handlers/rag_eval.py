from __future__ import annotations

import os
import asyncio
import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Literal, cast

import asyncpg
from groq import APIConnectionError, APIError, APITimeoutError, RateLimitError

from src.application.rag_eval.dataset_generator import (
    LlmRagEvalDatasetGenerator,
    MAX_ENTRIES_PER_LLM_BATCH,
)
from src.application.rag_eval.reporter import RagQualityReporter
from src.application.rag_eval.runner import RagEvalRunner, RagEvalTechnicalAnswerError
from src.application.rag_eval.service import RagEvalService
from src.application.rag_eval.schemas import RagEvalRun, RagQualityReport, new_eval_id
from src.infrastructure.db.repositories.knowledge_repository import KnowledgeRepository
from src.infrastructure.db.repositories.rag_eval_repository import RagEvalRepository
from src.infrastructure.llm.query_expander import GroqQueryExpander
from src.infrastructure.llm.rag_contract import KnowledgeSearchRepository
from src.infrastructure.llm.rag_service import RAGService
from src.infrastructure.logging.logger import get_logger
from src.infrastructure.llm.groq_keyring import has_configured_groq_api_key
from src.infrastructure.rag_eval.adapters import (
    GroqRagEvalJsonLlmAdapter,
    RagServiceRagEvalRetriever,
)
from src.infrastructure.queue.job_exceptions import PermanentJobError, TransientJobError

logger = get_logger(__name__)

RAG_EVAL_QUESTION_MODEL = os.getenv("RAG_EVAL_QUESTION_MODEL", "openai/gpt-oss-120b")
RAG_EVAL_JUDGE_MODEL = os.getenv("RAG_EVAL_JUDGE_MODEL", "llama-3.1-8b-instant")
RAG_EVAL_QUESTION_MAX_TOKENS = 6144
RAG_EVAL_JUDGE_MAX_TOKENS = 2048


RagEvalModeValue = Literal["retrieval_eval", "answer_quality_eval"]


def _rag_eval_mode_from_payload(value: object) -> RagEvalModeValue:
    if str(value or "").strip().lower() == "answer_quality_eval":
        return "answer_quality_eval"
    return "retrieval_eval"


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

    if not has_configured_groq_api_key():
        raise PermanentJobError("No Groq API keys are configured")

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


async def _resume_existing_rag_eval_dataset(
    *,
    rag_eval_repo: RagEvalRepository,
    runner: RagEvalRunner,
    reporter: RagQualityReporter,
    project_id: str,
    document_id: str,
    generator_model: str,
    control_callback,
    run_progress_callback,
) -> tuple[RagEvalRun, RagQualityReport] | None:
    dataset = await rag_eval_repo.get_latest_ready_dataset_with_questions(
        project_id=project_id,
        document_id=document_id,
    )
    if dataset is None or not dataset.questions:
        return None

    run = await rag_eval_repo.get_latest_resumable_run(
        project_id=project_id,
        document_id=document_id,
        dataset_id=dataset.id,
    )

    if run is None:
        run = RagEvalRun(
            id=new_eval_id("run"),
            dataset_id=dataset.id,
            project_id=project_id,
            document_id=document_id,
            status="running",
            generator_model=generator_model,
        )
    else:
        run.status = "running"
        run.finished_at = None
        if not run.generator_model:
            run.generator_model = generator_model
        run.results = await rag_eval_repo.load_run_results(run_id=run.id)

    await rag_eval_repo.create_run(run=run)

    completed_question_ids = {result.question_id for result in run.results}
    total_questions = len(dataset.questions)

    if run_progress_callback is not None:
        await run_progress_callback(len(completed_question_ids), total_questions)

    try:
        for index, question in enumerate(dataset.questions, start=1):
            if question.id in completed_question_ids:
                continue

            if control_callback is not None:
                await control_callback()

            try:
                result = await runner.run_question(
                    run_id=run.id,
                    project_id=project_id,
                    question=question,
                )
            except Exception as exc:
                result = runner.failed_result(
                    run_id=run.id,
                    question=question,
                    error=exc,
                    stage="resumed_rag_eval_question",
                )

            run.results.append(result)
            completed_question_ids.add(question.id)

            await rag_eval_repo.save_result(result=result)

            if run_progress_callback is not None:
                await run_progress_callback(
                    len(completed_question_ids), total_questions
                )
    except Exception:
        run.status = "failed"
        run.finished_at = datetime.now(UTC)
        await rag_eval_repo.finish_run(run=run)
        raise

    run.status = "completed"
    run.finished_at = datetime.now(UTC)

    report = reporter.build_report(run=run)
    await rag_eval_repo.finish_run(run=run)
    await rag_eval_repo.save_report(report=report)

    return run, report


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
    chunks = await rag_eval_repo.load_document_entries(
        project_id=project_id,
        document_id=document_id,
    )

    if not chunks:
        raise PermanentJobError("Document has no processed knowledge entries")

    total_batches = max(
        1,
        (len(chunks) + MAX_ENTRIES_PER_LLM_BATCH - 1) // MAX_ENTRIES_PER_LLM_BATCH,
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
        maximum=6144,
    )
    eval_mode = _rag_eval_mode_from_payload(payload.get("eval_mode"))

    knowledge_repo = KnowledgeRepository(db_pool)
    rag_service = RAGService(
        cast(KnowledgeSearchRepository, knowledge_repo),
        query_expander=GroqQueryExpander(),
    )

    question_llm = GroqRagEvalJsonLlmAdapter(
        model=RAG_EVAL_QUESTION_MODEL,
        max_tokens=question_max_tokens,
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

        judge_max_tokens = _coerce_int(
            payload.get("judge_llm_max_tokens"),
            default=RAG_EVAL_JUDGE_MAX_TOKENS,
            minimum=512,
            maximum=4096,
        )
        judge_llm = GroqRagEvalJsonLlmAdapter(
            model=RAG_EVAL_JUDGE_MODEL,
            max_tokens=judge_max_tokens,
        )
        runner = RagEvalRunner(
            retriever=RagServiceRagEvalRetriever(rag_service),
            answerer=ProductionRagEvalAnswerer(),
            answer_judge=LlmRagEvalAnswerJudge(llm=judge_llm),
            mode=eval_mode,
            retrieval_limit=retrieval_limit,
        )
    else:
        runner = RagEvalRunner(
            retriever=RagServiceRagEvalRetriever(rag_service),
            mode=eval_mode,
            retrieval_limit=retrieval_limit,
        )

    service = RagEvalService(
        entry_source=rag_eval_repo,
        dataset_generator=dataset_generator,
        runner=runner,
        reporter=RagQualityReporter(),
        store=rag_eval_repo,
        report_sink=None,
    )

    source_entry_count = len(chunks)
    total_batches = max(
        1,
        (len(chunks) + MAX_ENTRIES_PER_LLM_BATCH - 1) // MAX_ENTRIES_PER_LLM_BATCH,
    )

    base_progress: dict[str, object] = {
        "project_id": project_id,
        "document_id": document_id,
        "requested_by": requested_by,
        "source_entry_count": source_entry_count,
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
            "message": "Generating RAG eval questions from document entries",
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
        resumed = await _resume_existing_rag_eval_dataset(
            rag_eval_repo=rag_eval_repo,
            runner=runner,
            reporter=service._reporter,
            project_id=project_id,
            document_id=document_id,
            generator_model=RAG_EVAL_QUESTION_MODEL,
            control_callback=_control_callback,
            run_progress_callback=_on_run_progress,
        )

        if resumed is None:
            run, report = await service.generate_dataset_and_run(
                project_id=project_id,
                document_id=document_id,
                progress_callback=_on_dataset_progress,
                control_callback=_control_callback,
                run_progress_callback=_on_run_progress,
            )
        else:
            run, report = resumed
    except RagEvalTechnicalAnswerError as exc:
        await _write_rag_eval_progress(
            db_pool=db_pool,
            job_id=job_id,
            progress={
                **base_progress,
                "stage": "paused_provider_limit",
                "status": "paused",
                "message": "RAG eval paused: provider returned a technical answer fallback, likely Groq quota/rate limit exhaustion",
                "percent": current_control_progress.get("percent", 0.0),
                "updated_at": _utc_now_iso(),
            },
        )
        raise _transient_from_provider_error(exc) from exc
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
