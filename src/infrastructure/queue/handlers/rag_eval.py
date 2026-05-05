from __future__ import annotations

import re
from collections.abc import Mapping
from typing import cast

import asyncpg
from groq import APIConnectionError, APIError, APITimeoutError, RateLimitError

from src.application.rag_eval.dataset_generator import LlmRagEvalDatasetGenerator
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

    json_llm = GroqRagEvalJsonLlmAdapter(max_tokens=llm_max_tokens)
    dataset_generator = LlmRagEvalDatasetGenerator(
        llm=json_llm,
        model_name=settings.GROQ_MODEL,
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
            "source_chunk_count": len(chunks),
            "questions_per_chunk": questions_per_chunk,
            "target_questions": full_document_target,
            "retrieval_limit": retrieval_limit,
        },
    )

    run, report = await service.generate_dataset_and_run(
        project_id=project_id,
        document_id=document_id,
        max_questions=full_document_target,
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
