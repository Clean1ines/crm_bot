from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_answer_resolution_progress_metrics_are_persisted_before_publication() -> None:
    structured_source = Path(
        "src/application/services/knowledge_structured_ingestion_service.py"
    ).read_text(encoding="utf-8")
    answer_resolution_source = (
        ROOT / "src/application/services/knowledge_answer_resolution_service.py"
    ).read_text(encoding="utf-8")

    progress_index = structured_source.index(
        "async def persist_answer_resolution_progress"
    )
    tighten_index = structured_source.index(
        "KnowledgeAnswerResolutionService().resolve_compiled_answer_cases"
    )
    publish_index = structured_source.index(
        "canonical_entries = _canonical_entries_from_preprocessing_result"
    )

    assert progress_index < tighten_index < publish_index

    progress_slice = structured_source[progress_index:publish_index]
    assert '"stage": "answer_resolution"' in progress_slice
    assert "await repo.update_document_preprocessing_status" in progress_slice
    assert "metrics" in progress_slice
    assert "on_progress=persist_answer_resolution_progress" in progress_slice

    resolver_index = answer_resolution_source.index(
        "async def _resolve_compiled_answer_cases"
    )
    resolver_slice = answer_resolution_source[resolver_index:]

    assert '"decision_trace": []' in resolver_slice
    assert 'metrics["decision_trace"] = decision_trace[-200:]' in resolver_slice
    assert 'metrics["resolved_answer_count"]' in resolver_slice
    assert 'metrics["kept_separate_count"]' in resolver_slice


def test_processing_report_exposes_answer_resolution_step() -> None:
    source = Path(
        "src/application/services/knowledge_processing_report_builder.py"
    ).read_text(encoding="utf-8")

    assert 'id="answer_resolution"' in source
    assert 'label="Разрешение ответов"' in source
    assert "answer_resolution_metrics" in source
    assert 'current_stage == "answer_resolution"' in source


def test_frontend_references_answer_resolution_step_key() -> None:
    source = Path("frontend/src/pages/knowledge/KnowledgePage.tsx").read_text(
        encoding="utf-8"
    )

    assert 'ANSWER_RESOLUTION_STEP_ID = "answer_resolution"' in source
