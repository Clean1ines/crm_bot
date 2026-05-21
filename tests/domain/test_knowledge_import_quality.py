from __future__ import annotations

from src.domain.project_plane.knowledge_import_quality import (
    IMPORT_QUALITY_ACTION_CONTINUE,
    IMPORT_QUALITY_ACTION_REPLACE_OR_REVIEW_DOCUMENT,
    IMPORT_QUALITY_ACTION_REVIEW_SOURCE_UNITS,
    IMPORT_QUALITY_ACTION_WAIT_FOR_PROCESSING,
    IMPORT_QUALITY_STATUS_GOOD,
    IMPORT_QUALITY_STATUS_NEEDS_REVIEW,
    IMPORT_QUALITY_STATUS_UNSAFE,
    ImportQualitySourceUnit,
    build_document_import_quality_report,
)


def test_import_quality_good_for_structured_document() -> None:
    report = build_document_import_quality_report(
        document_id="doc-1",
        file_name="knowledge.md",
        document_status="processed",
        preprocessing_status="completed",
        preprocessing_metrics=None,
        source_units=(
            ImportQualitySourceUnit(
                content="Delivery rules. " * 20,
                section_title="Delivery",
            ),
            ImportQualitySourceUnit(
                content="Payment and refund policy. " * 20,
                section_title="Payments",
            ),
        ),
    )

    assert report.status == IMPORT_QUALITY_STATUS_GOOD
    assert report.safe_to_compile is True
    assert report.source_format == "md"
    assert report.source_units_count == 2
    assert report.warnings == ()
    assert report.recommended_action == IMPORT_QUALITY_ACTION_CONTINUE


def test_import_quality_unsafe_without_source_units() -> None:
    report = build_document_import_quality_report(
        document_id="doc-1",
        file_name="empty.pdf",
        document_status="processed",
        preprocessing_status="completed",
        preprocessing_metrics=None,
        source_units=(),
    )

    assert report.status == IMPORT_QUALITY_STATUS_UNSAFE
    assert report.safe_to_compile is False
    assert report.source_units_count == 0
    assert {warning.code for warning in report.warnings} == {
        "no_source_units",
        "very_little_text",
    }
    assert report.recommended_action == IMPORT_QUALITY_ACTION_REPLACE_OR_REVIEW_DOCUMENT


def test_import_quality_needs_review_for_table_like_content() -> None:
    report = build_document_import_quality_report(
        document_id="doc-1",
        file_name="prices.txt",
        document_status="processed",
        preprocessing_status="completed",
        preprocessing_metrics=None,
        source_units=(
            ImportQualitySourceUnit(
                content=(
                    "Plan | Price | Limit\n"
                    "Basic | 10 | 100\n"
                    "Pro | 20 | 500\n"
                    "Enterprise | custom | custom"
                ),
                section_title="Prices",
            ),
            ImportQualitySourceUnit(
                content="Additional pricing conditions. " * 10,
                section_title="Conditions",
            ),
        ),
    )

    assert report.status == IMPORT_QUALITY_STATUS_NEEDS_REVIEW
    assert report.safe_to_compile is True
    assert report.table_like_units_count == 1
    assert "table_like_content" in {warning.code for warning in report.warnings}
    assert report.recommended_action == IMPORT_QUALITY_ACTION_REVIEW_SOURCE_UNITS


def test_import_quality_waits_for_processing() -> None:
    report = build_document_import_quality_report(
        document_id="doc-1",
        file_name="knowledge.md",
        document_status="processing",
        preprocessing_status="processing",
        preprocessing_metrics=None,
        source_units=(
            ImportQualitySourceUnit(
                content="This document is still being processed. " * 10,
                section_title="Processing",
            ),
        ),
    )

    assert report.status == IMPORT_QUALITY_STATUS_NEEDS_REVIEW
    assert report.safe_to_compile is False
    assert "processing_not_finished" in {warning.code for warning in report.warnings}
    assert report.recommended_action == IMPORT_QUALITY_ACTION_WAIT_FOR_PROCESSING


def test_import_quality_waits_for_processing_without_source_units() -> None:
    report = build_document_import_quality_report(
        document_id="doc-1",
        file_name="knowledge.md",
        document_status="processing",
        preprocessing_status="processing",
        preprocessing_metrics=None,
        source_units=(),
    )

    assert report.status == IMPORT_QUALITY_STATUS_NEEDS_REVIEW
    assert report.safe_to_compile is False
    assert {
        "processing_not_finished",
        "no_source_units",
        "very_little_text",
    }.issubset({warning.code for warning in report.warnings})
    assert report.recommended_action == IMPORT_QUALITY_ACTION_WAIT_FOR_PROCESSING
