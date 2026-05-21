from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field


IMPORT_QUALITY_STATUS_GOOD = "good"
IMPORT_QUALITY_STATUS_NEEDS_REVIEW = "needs_review"
IMPORT_QUALITY_STATUS_UNSAFE = "unsafe"

IMPORT_QUALITY_ACTION_CONTINUE = "continue_to_knowledge_compilation"
IMPORT_QUALITY_ACTION_REVIEW_SOURCE_UNITS = "review_source_units"
IMPORT_QUALITY_ACTION_WAIT_FOR_PROCESSING = "wait_for_processing"
IMPORT_QUALITY_ACTION_REPLACE_OR_REVIEW_DOCUMENT = "replace_or_review_document"

_SHORT_UNIT_CHAR_LIMIT = 80
_MIN_HEALTHY_TEXT_CHARS = 200
_MANY_SHORT_UNITS_RATIO = 0.4
_MANY_EMPTY_UNITS_RATIO = 0.8


@dataclass(frozen=True, slots=True)
class ImportQualitySourceUnit:
    content: str
    section_title: str = ""
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DocumentImportIssue:
    code: str
    severity: str
    message: str


@dataclass(frozen=True, slots=True)
class DocumentImportQualityReport:
    document_id: str
    status: str
    safe_to_compile: bool
    source_format: str
    extracted_text_chars: int
    source_units_count: int
    empty_units_count: int
    short_units_count: int
    table_like_units_count: int
    duplicated_headings_count: int
    source_refs_ready: bool
    warnings: tuple[DocumentImportIssue, ...]
    recommended_action: str


def build_document_import_quality_report(
    *,
    document_id: str,
    file_name: str,
    document_status: str,
    preprocessing_status: str | None,
    preprocessing_metrics: object | None,
    source_units: Sequence[ImportQualitySourceUnit],
) -> DocumentImportQualityReport:
    normalized_document_status = _normalized_status(document_status)
    normalized_preprocessing_status = _normalized_status(preprocessing_status)
    source_format = _source_format(file_name)
    metrics = _metrics_mapping(preprocessing_metrics)

    extracted_text_chars = _extracted_text_chars(source_units, metrics)
    source_units_count = len(source_units)
    empty_units_count = sum(1 for unit in source_units if not unit.content.strip())
    short_units_count = sum(
        1
        for unit in source_units
        if 0 < len(unit.content.strip()) < _SHORT_UNIT_CHAR_LIMIT
    )
    table_like_units_count = sum(1 for unit in source_units if _looks_table_like(unit))
    duplicated_headings_count = _duplicated_headings_count(source_units)
    source_refs_ready = (
        source_units_count > 0 and empty_units_count < source_units_count
    )

    warnings = _build_warnings(
        document_status=normalized_document_status,
        preprocessing_status=normalized_preprocessing_status,
        extracted_text_chars=extracted_text_chars,
        source_units_count=source_units_count,
        empty_units_count=empty_units_count,
        short_units_count=short_units_count,
        table_like_units_count=table_like_units_count,
        duplicated_headings_count=duplicated_headings_count,
    )

    status = _report_status(
        document_status=normalized_document_status,
        preprocessing_status=normalized_preprocessing_status,
        extracted_text_chars=extracted_text_chars,
        source_units_count=source_units_count,
        empty_units_count=empty_units_count,
        warnings=warnings,
    )
    safe_to_compile = status != IMPORT_QUALITY_STATUS_UNSAFE and not _is_processing(
        normalized_document_status,
        normalized_preprocessing_status,
    )
    recommended_action = _recommended_action(
        status=status,
        document_status=normalized_document_status,
        preprocessing_status=normalized_preprocessing_status,
        warnings=warnings,
    )

    return DocumentImportQualityReport(
        document_id=document_id,
        status=status,
        safe_to_compile=safe_to_compile,
        source_format=source_format,
        extracted_text_chars=extracted_text_chars,
        source_units_count=source_units_count,
        empty_units_count=empty_units_count,
        short_units_count=short_units_count,
        table_like_units_count=table_like_units_count,
        duplicated_headings_count=duplicated_headings_count,
        source_refs_ready=source_refs_ready,
        warnings=warnings,
        recommended_action=recommended_action,
    )


def _normalized_status(value: str | None) -> str:
    return (value or "").strip().lower()


def _source_format(file_name: str) -> str:
    cleaned = file_name.strip().lower()
    if "." not in cleaned:
        return "unknown"

    suffix = cleaned.rsplit(".", 1)[-1].strip()
    return suffix or "unknown"


def _metrics_mapping(value: object | None) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _extracted_text_chars(
    source_units: Sequence[ImportQualitySourceUnit],
    metrics: Mapping[str, object],
) -> int:
    metric_value = metrics.get("extracted_text_chars")
    parsed_metric = _positive_int(metric_value)
    if parsed_metric is not None:
        return parsed_metric

    return sum(len(unit.content or "") for unit in source_units)


def _positive_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    if isinstance(value, float) and value >= 0 and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _looks_table_like(unit: ImportQualitySourceUnit) -> bool:
    content = unit.content.strip()
    if not content:
        return False

    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if not lines:
        return False

    pipe_rows = sum(1 for line in lines if line.count("|") >= 2)
    tab_rows = sum(1 for line in lines if "\t" in line)
    spaced_column_rows = sum(
        1 for line in lines if re.search(r"\S\s{2,}\S\s{2,}\S", line)
    )

    return pipe_rows >= 2 or tab_rows >= 2 or spaced_column_rows >= 2


def _duplicated_headings_count(source_units: Sequence[ImportQualitySourceUnit]) -> int:
    seen: set[str] = set()
    duplicated: set[str] = set()

    for unit in source_units:
        normalized = " ".join(unit.section_title.lower().split())
        if not normalized:
            continue
        if normalized in seen:
            duplicated.add(normalized)
        seen.add(normalized)

    return len(duplicated)


def _build_warnings(
    *,
    document_status: str,
    preprocessing_status: str,
    extracted_text_chars: int,
    source_units_count: int,
    empty_units_count: int,
    short_units_count: int,
    table_like_units_count: int,
    duplicated_headings_count: int,
) -> tuple[DocumentImportIssue, ...]:
    warnings: list[DocumentImportIssue] = []

    if document_status in {"error", "failed"} or preprocessing_status == "failed":
        warnings.append(
            DocumentImportIssue(
                code="processing_failed",
                severity="error",
                message="Document processing failed.",
            )
        )

    if document_status == "cancelled" or preprocessing_status == "cancelled":
        warnings.append(
            DocumentImportIssue(
                code="processing_cancelled",
                severity="warning",
                message="Document processing was cancelled.",
            )
        )

    if _is_processing(document_status, preprocessing_status):
        warnings.append(
            DocumentImportIssue(
                code="processing_not_finished",
                severity="info",
                message="Document processing is not finished yet.",
            )
        )

    if source_units_count == 0:
        warnings.append(
            DocumentImportIssue(
                code="no_source_units",
                severity="error",
                message="No source units were extracted from the document.",
            )
        )

    if extracted_text_chars < _MIN_HEALTHY_TEXT_CHARS:
        warnings.append(
            DocumentImportIssue(
                code="very_little_text",
                severity="warning",
                message="Very little text was extracted from the document.",
            )
        )

    if source_units_count > 0:
        empty_ratio = empty_units_count / source_units_count
        short_ratio = short_units_count / source_units_count

        if empty_ratio >= _MANY_EMPTY_UNITS_RATIO:
            warnings.append(
                DocumentImportIssue(
                    code="many_empty_units",
                    severity="error",
                    message="Most extracted source units are empty.",
                )
            )

        if short_units_count >= 3 and short_ratio >= _MANY_SHORT_UNITS_RATIO:
            warnings.append(
                DocumentImportIssue(
                    code="many_short_units",
                    severity="warning",
                    message="Many extracted source units are very short.",
                )
            )

    if table_like_units_count > 0:
        warnings.append(
            DocumentImportIssue(
                code="table_like_content",
                severity="warning",
                message="Some source units look table-like and should be reviewed manually.",
            )
        )

    if duplicated_headings_count > 0:
        warnings.append(
            DocumentImportIssue(
                code="duplicated_headings",
                severity="warning",
                message="Some section headings are duplicated.",
            )
        )

    return tuple(warnings)


def _report_status(
    *,
    document_status: str,
    preprocessing_status: str,
    extracted_text_chars: int,
    source_units_count: int,
    empty_units_count: int,
    warnings: Sequence[DocumentImportIssue],
) -> str:
    warning_codes = {warning.code for warning in warnings}

    if _is_processing(document_status, preprocessing_status):
        return IMPORT_QUALITY_STATUS_NEEDS_REVIEW

    if (
        document_status in {"error", "failed"}
        or preprocessing_status == "failed"
        or "no_source_units" in warning_codes
        or "many_empty_units" in warning_codes
        or extracted_text_chars <= 0
    ):
        return IMPORT_QUALITY_STATUS_UNSAFE

    if source_units_count > 0 and empty_units_count >= source_units_count:
        return IMPORT_QUALITY_STATUS_UNSAFE

    if warnings:
        return IMPORT_QUALITY_STATUS_NEEDS_REVIEW

    return IMPORT_QUALITY_STATUS_GOOD


def _recommended_action(
    *,
    status: str,
    document_status: str,
    preprocessing_status: str,
    warnings: Sequence[DocumentImportIssue],
) -> str:
    if _is_processing(document_status, preprocessing_status):
        return IMPORT_QUALITY_ACTION_WAIT_FOR_PROCESSING

    if status == IMPORT_QUALITY_STATUS_UNSAFE:
        return IMPORT_QUALITY_ACTION_REPLACE_OR_REVIEW_DOCUMENT

    if warnings:
        return IMPORT_QUALITY_ACTION_REVIEW_SOURCE_UNITS

    return IMPORT_QUALITY_ACTION_CONTINUE


def _is_processing(document_status: str, preprocessing_status: str) -> bool:
    return document_status in {"pending", "processing"} or preprocessing_status in {
        "processing",
        "pending",
    }
