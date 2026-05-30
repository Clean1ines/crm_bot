from __future__ import annotations


import json
from collections.abc import (
    Mapping,
    Sequence,
)
from src.application.errors import ValidationError
from src.domain.project_plane.json_types import (
    JsonObject,
    JsonValue,
)
from src.domain.project_plane.knowledge_preprocessing import (
    KnowledgePreprocessingEntry,
    KnowledgePreprocessingMode,
    KnowledgePreprocessingResult,
    KnowledgePreprocessingValidationError,
)


def _clean_optional_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.strip().split())


KCD_STAGE_K_CANCELLED_ERROR = "Knowledge preprocessing cancelled by operator"


def source_excerpt_to_text(value: object) -> str:
    if isinstance(value, tuple):
        return "\n\n".join(
            _clean_optional_text(str(part))
            for part in value
            if _clean_optional_text(str(part))
        )
    return _clean_optional_text(str(value or ""))


def build_preprocessing_failure_status_message(exc: Exception) -> str:
    if str(exc) == KCD_STAGE_K_CANCELLED_ERROR:
        return (
            "Обработка остановлена: прогресс до последнего завершённого шага сохранён"
        )
    if isinstance(exc, KnowledgePreprocessingValidationError):
        return "Ошибка предобработки: LLM вернула данные в неподдерживаемом формате"
    if isinstance(exc, ValidationError):
        return "Ошибка предобработки: результаты не прошли проверку перед публикацией"
    if isinstance(exc, json.JSONDecodeError):
        return "Ошибка предобработки: LLM не вернула корректный JSON"
    return "Ошибка предобработки: pipeline остановлен до публикации результатов"


def json_metric_int(metrics: Mapping[str, JsonValue], key: str) -> int:
    value = metrics.get(key)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return 0


def build_preprocessing_result_from_entries(
    *,
    mode: KnowledgePreprocessingMode,
    template: KnowledgePreprocessingResult,
    entries: Sequence[KnowledgePreprocessingEntry],
    metrics: JsonObject,
) -> KnowledgePreprocessingResult:
    return KnowledgePreprocessingResult(
        mode=mode,
        prompt_version=template.prompt_version,
        model=template.model,
        entries=tuple(entries),
        metrics=metrics,
    )


__all__ = [
    "source_excerpt_to_text",
    "build_preprocessing_failure_status_message",
    "json_metric_int",
    "build_preprocessing_result_from_entries",
]
