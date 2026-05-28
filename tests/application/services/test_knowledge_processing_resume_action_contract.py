from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.application.services.knowledge_processing_report_builder import (
    build_knowledge_processing_report,
)

ROOT = Path(__file__).resolve().parents[3]
SERVICE = ROOT / "src/application/services/knowledge_service.py"
HTTP = ROOT / "src/interfaces/http/knowledge.py"


@dataclass(frozen=True)
class Document:
    status: str = "error"
    preprocessing_status: str = "failed"
    preprocessing_error: str | None = "Остановлено пользователем"
    preprocessing_metrics: object = None
    structured_entries: int | None = 0
    chunk_count: int = 49


@dataclass(frozen=True)
class Summary:
    raw_count: int = 1
    total_count: int = 1
    grounded_count: int = 1
    rejected_count: int = 0


def test_cancelled_faq_document_gets_resume_processing_action() -> None:
    report = build_knowledge_processing_report(
        document_id="doc-1",
        document=Document(
            preprocessing_metrics={
                "source_unit_count": 49,
                "surface_compiler_run_id": "run-1",
                "elapsed_seconds": 37.5,
            },
        ),
        batches=(),
        candidate_summary=Summary(),
    )

    assert report.recoverable is True
    assert any(action.id == "resume_processing" for action in report.actions)
    assert not any(action.id == "cancel" for action in report.actions)


def test_resume_backend_contract_is_explicit_not_late_write() -> None:
    service = SERVICE.read_text(encoding="utf-8")
    http = HTTP.read_text(encoding="utf-8")

    assert "resume_document_processing" in service
    assert "resume_requested" in service
    assert "elapsed_before_resume_seconds" in service
    assert "processing_started_at_epoch" in service
    assert '@router.post("/{document_id}/resume-processing")' in http
    assert "TASK_PROCESS_KNOWLEDGE_UPLOAD" in http
