from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
PERSISTENCE = (
    ROOT / "src/infrastructure/db/repositories/knowledge_document_persistence.py"
)


def _assert_cancel_guard_uses_lifecycle_constant(source: str) -> None:
    assert "from src.domain.project_plane.knowledge_document_lifecycle import" in source
    assert "LEGACY_USER_CANCELLED_MESSAGE" in source
    assert "PROCESSING_CANCELLED_REASON" not in source


def test_cancelled_documents_are_not_marked_processing_or_processed_by_late_status() -> (
    None
):
    source = PERSISTENCE.read_text(encoding="utf-8")

    _assert_cancel_guard_uses_lifecycle_constant(source)
    assert "$1 IN ('processing', 'processed')" in source
    assert "preprocessing_status = 'failed'" in source
    assert "preprocessing_error = $4" in source


def test_cancelled_documents_are_not_marked_preprocessing_processing_or_completed() -> (
    None
):
    source = PERSISTENCE.read_text(encoding="utf-8")

    _assert_cancel_guard_uses_lifecycle_constant(source)
    assert "$2 IN ('processing', 'completed')" in source
    assert "preprocessing_status = 'failed'" in source
    assert "preprocessing_error = $8" in source


def test_cancelled_documents_do_not_accept_late_preprocessing_metric_merges() -> None:
    source = PERSISTENCE.read_text(encoding="utf-8")

    _assert_cancel_guard_uses_lifecycle_constant(source)
    assert "SET preprocessing_metrics = COALESCE(preprocessing_metrics" in source
    assert "preprocessing_error = $4" in source
