from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol

from src.application.dto.knowledge_dto import (
    KnowledgeProcessingActionDto,
    KnowledgeProcessingReportDto,
    KnowledgeProcessingStepDto,
)
from src.domain.project_plane.json_types import JsonObject


class KnowledgeProcessingDocumentLike(Protocol):
    @property
    def status(self) -> str: ...

    @property
    def preprocessing_status(self) -> str | None: ...

    @property
    def preprocessing_metrics(self) -> object: ...

    @property
    def structured_entries(self) -> int | None: ...

    @property
    def chunk_count(self) -> int: ...


class KnowledgeProcessingBatchLike(Protocol):
    @property
    def status(self) -> str: ...

    @property
    def batch_count(self) -> int: ...

    @property
    def tokens_input(self) -> int: ...

    @property
    def tokens_output(self) -> int: ...

    @property
    def tokens_total(self) -> int: ...


class KnowledgeAnswerCandidateSummaryLike(Protocol):
    @property
    def raw_count(self) -> int: ...

    @property
    def total_count(self) -> int: ...

    @property
    def grounded_count(self) -> int: ...

    @property
    def rejected_count(self) -> int: ...


def _answer_resolution_metrics(metrics: JsonObject) -> JsonObject:
    value = metrics.get("answer_resolution")
    return dict(value) if isinstance(value, Mapping) else {}


def _json_int_metric(metrics: JsonObject, key: str) -> int:
    value = metrics.get(key)
    if isinstance(value, bool) or value is None:
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return 0


def _answer_resolution_report_status(
    metrics: JsonObject,
    *,
    is_processing: bool,
) -> str:
    status = str(metrics.get("status") or "")
    if status == "failed_fallback_published":
        return "failed"
    if status in {"processing", "completed", "failed"}:
        return status
    if is_processing:
        return "waiting"
    return "completed" if metrics else "pending"


def _batch_status_count(
    batches: Sequence[KnowledgeProcessingBatchLike],
    status: str,
) -> int:
    return sum(1 for batch in batches if batch.status == status)


def _knowledge_processing_title(
    *,
    document_status: str,
    preprocessing_status: str,
) -> str:
    if preprocessing_status == "completed" or document_status == "processed":
        return "Готово: база знаний обновлена"
    if preprocessing_status == "failed" or document_status == "error":
        return "Обработка остановилась, но прогресс сохранён"
    if preprocessing_status == "cancelled" or document_status == "cancelled":
        return "Обработка остановлена"
    if preprocessing_status == "processing" or document_status in {
        "processing",
        "pending",
    }:
        return "Ищем ответы в документе"
    return "Документ подготовлен"


def _knowledge_processing_message(
    *,
    batch_total: int,
    batch_completed: int,
    batch_failed: int,
    raw_answer_count: int,
    published_answer_count: int,
) -> str:
    if batch_failed > 0 and published_answer_count > 0:
        return (
            f"Опубликовано ответов: {published_answer_count}. "
            f"Обработано {batch_completed} из {batch_total} частей. "
            f"Черновиков сохранено: {raw_answer_count}. "
            "Проблемные части можно повторить позже."
        )
    if batch_failed > 0:
        return (
            f"Обработано {batch_completed} из {batch_total} частей. "
            f"Найдено черновиков: {raw_answer_count}. "
            "Проблемные части можно повторить без потери уже сохранённого прогресса."
        )
    if batch_total > 0 and batch_completed < batch_total:
        return (
            f"Обработано {batch_completed} из {batch_total} частей. "
            f"Найдено черновиков: {raw_answer_count}. "
            "Черновики сохраняются после каждого шага."
        )
    if published_answer_count > 0:
        return (
            f"Опубликовано ответов: {published_answer_count}. "
            "Черновики можно проверить или удалить позже."
        )
    if raw_answer_count > 0:
        return f"Найдено черновиков: {raw_answer_count}. Их можно проверить и опубликовать."
    return "Документ ожидает обработки или пока не дал пригодных ответов."


def _knowledge_processing_actions(
    *,
    batch_failed: int,
    raw_answer_count: int,
    published_answer_count: int,
    is_processing: bool,
) -> tuple[KnowledgeProcessingActionDto, ...]:
    actions: list[KnowledgeProcessingActionDto] = []
    if is_processing:
        actions.append(
            KnowledgeProcessingActionDto(
                id="cancel",
                label="Остановить обработку",
                kind="destructive",
            )
        )
    if batch_failed > 0:
        actions.append(
            KnowledgeProcessingActionDto(
                id="retry_failed_batches",
                label="Повторить проблемные части",
                kind="primary",
            )
        )
    if raw_answer_count > published_answer_count:
        actions.append(
            KnowledgeProcessingActionDto(
                id="publish_ready",
                label="Опубликовать готовые ответы",
                kind="primary",
                enabled=not is_processing,
            )
        )
    return tuple(actions)


def build_knowledge_processing_report(
    *,
    document_id: str,
    document: KnowledgeProcessingDocumentLike,
    batches: Sequence[KnowledgeProcessingBatchLike],
    candidate_summary: KnowledgeAnswerCandidateSummaryLike,
) -> KnowledgeProcessingReportDto:
    batch_total = max((batch.batch_count for batch in batches), default=0)
    batch_completed = _batch_status_count(batches, "completed")
    batch_failed = _batch_status_count(batches, "failed")
    batch_processing = _batch_status_count(batches, "processing")
    batch_pending = _batch_status_count(batches, "pending")
    is_processing = document.status in {"processing", "pending"} or (
        document.preprocessing_status == "processing"
    )
    published_answer_count = int(document.structured_entries or 0)
    document_metrics = (
        dict(document.preprocessing_metrics)
        if isinstance(document.preprocessing_metrics, Mapping)
        else {}
    )
    answer_resolution_metrics = _answer_resolution_metrics(document_metrics)
    current_stage = str(document_metrics.get("stage") or "")
    answer_resolution_status = _answer_resolution_report_status(
        answer_resolution_metrics,
        is_processing=is_processing,
    )
    if current_stage == "answer_resolution" and answer_resolution_status == "waiting":
        answer_resolution_status = "processing"

    answer_resolution_total = _json_int_metric(
        answer_resolution_metrics,
        "suspect_case_count",
    )
    answer_resolution_current = _json_int_metric(
        answer_resolution_metrics,
        "processed_case_count",
    )
    answer_resolution_final_count = (
        _json_int_metric(answer_resolution_metrics, "final_entry_count")
        or _json_int_metric(answer_resolution_metrics, "entry_count_after")
        or _json_int_metric(document_metrics, "canonical_entry_count")
        or _json_int_metric(document_metrics, "published_entry_count")
    )

    steps = (
        KnowledgeProcessingStepDto(
            id="prepare",
            label="Подготовка документа",
            status="completed"
            if batch_total > 0 or document.chunk_count > 0
            else "pending",
            current=document.chunk_count,
            total=document.chunk_count,
            message="Исходные части документа сохранены",
        ),
        KnowledgeProcessingStepDto(
            id="extract",
            label="Извлечение ответов",
            status=(
                "failed"
                if batch_failed > 0
                else "completed"
                if batch_total > 0 and batch_completed >= batch_total
                else "processing"
                if is_processing
                else "pending"
            ),
            current=batch_completed,
            total=batch_total,
            message=f"Черновиков найдено: {candidate_summary.raw_count}",
        ),
        KnowledgeProcessingStepDto(
            id="answer_resolution",
            label="Разрешение ответов",
            status=answer_resolution_status,
            current=answer_resolution_current,
            total=answer_resolution_total,
            message=(
                f"Проверено случаев: {answer_resolution_current} из {answer_resolution_total}"
                if answer_resolution_total > 0
                else "Ожидаем завершения извлечения"
            ),
        ),
        KnowledgeProcessingStepDto(
            id="publish",
            label="Публикация в базу знаний",
            status=(
                "completed"
                if published_answer_count > 0
                else "waiting"
                if current_stage == "answer_resolution" and is_processing
                else "pending"
            ),
            current=published_answer_count,
            total=max(answer_resolution_final_count, published_answer_count),
            message=(
                "Ожидаем завершения разрешения похожих ответов"
                if current_stage == "answer_resolution" and is_processing
                else f"Опубликовано ответов: {published_answer_count}"
            ),
        ),
    )

    metrics: JsonObject = {
        "source_chunk_count": _json_int_metric(
            document_metrics,
            "source_chunk_count",
        ),
        "raw_source_chunk_count": _json_int_metric(
            document_metrics,
            "raw_source_chunk_count",
        ),
        "markdown_semantic_units_total": _json_int_metric(
            document_metrics,
            "markdown_semantic_units_total",
        ),
        "markdown_child_sections_total": _json_int_metric(
            document_metrics,
            "markdown_child_sections_total",
        ),
        "canonical_entry_count": (
            _json_int_metric(document_metrics, "canonical_entry_count")
            or document.chunk_count
        ),
        "retrieval_surface_entry_count": document.structured_entries,
        "batch_total": batch_total,
        "batch_completed": batch_completed,
        "batch_failed": batch_failed,
        "batch_processing": batch_processing,
        "batch_pending": batch_pending,
        "draft_answer_count": candidate_summary.raw_count,
        "answer_candidate_count": candidate_summary.total_count,
        "published_answer_count": published_answer_count,
        "grounded_candidate_count": candidate_summary.grounded_count,
        "rejected_answer_count": candidate_summary.rejected_count,
        "tokens_input": sum(batch.tokens_input for batch in batches),
        "tokens_output": sum(batch.tokens_output for batch in batches),
        "tokens_total": sum(batch.tokens_total for batch in batches),
        "answer_resolution": answer_resolution_metrics,
    }

    if current_stage == "answer_resolution" and is_processing:
        title = "Разрешаем похожие ответы"
        message = (
            "Черновики уже сохранены. Сейчас система проверяет смысловые дубли "
            "и выбирает итоговые ответы перед публикацией."
        )
    else:
        title = (
            "Опубликовано частично: есть проблемные части"
            if batch_failed > 0 and published_answer_count > 0
            else _knowledge_processing_title(
                document_status=document.status,
                preprocessing_status=document.preprocessing_status or "",
            )
        )
        message = _knowledge_processing_message(
            batch_total=batch_total,
            batch_completed=batch_completed,
            batch_failed=batch_failed,
            raw_answer_count=candidate_summary.raw_count,
            published_answer_count=published_answer_count,
        )

    return KnowledgeProcessingReportDto(
        document_id=document_id,
        status=document.preprocessing_status or document.status,
        title=title,
        message=message,
        recoverable=batch_failed > 0
        or candidate_summary.raw_count > published_answer_count,
        steps=steps,
        actions=_knowledge_processing_actions(
            batch_failed=batch_failed,
            raw_answer_count=candidate_summary.raw_count,
            published_answer_count=published_answer_count,
            is_processing=is_processing,
        ),
        metrics=metrics,
    )
