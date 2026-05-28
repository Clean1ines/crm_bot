from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
PERSISTENCE = ROOT / "src/infrastructure/db/repositories/knowledge_document_persistence.py"


def test_cancelled_documents_are_not_marked_processed_by_late_success() -> None:
    source = PERSISTENCE.read_text(encoding="utf-8")

    assert "PROCESSING_CANCELLED_REASON" in source
    assert "$1 = 'processed'" in source
    assert "preprocessing_status = 'failed'" in source
    assert "preprocessing_error = $4" in source


def test_cancelled_documents_are_not_marked_preprocessing_completed_by_late_success() -> None:
    source = PERSISTENCE.read_text(encoding="utf-8")

    assert "$2 = 'completed'" in source
    assert "preprocessing_status = 'failed'" in source
    assert "preprocessing_error = $8" in source
