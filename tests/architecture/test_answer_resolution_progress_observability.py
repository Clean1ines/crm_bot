from __future__ import annotations

from pathlib import Path


def test_answer_resolution_progress_metrics_are_persisted_before_publication() -> None:
    source = Path("src/application/services/knowledge_ingestion_service.py").read_text(
        encoding="utf-8"
    )

    progress_index = source.index("async def persist_answer_resolution_progress")
    tighten_index = source.index("await _resolve_compiled_answer_cases")
    publish_index = source.index(
        "canonical_entries = _canonical_entries_from_preprocessing_result",
        tighten_index,
    )
    progress_slice = source[progress_index:publish_index]

    assert progress_index < tighten_index < publish_index
    assert '"stage": "answer_resolution"' in progress_slice
    assert (
        '"processed_case_count"'
        in source[
            source.index("async def _resolve_compiled_answer_cases") : publish_index
        ]
    )
    assert "on_progress=persist_answer_resolution_progress" in progress_slice


def test_processing_report_exposes_answer_resolution_step() -> None:
    source = Path("src/application/services/knowledge_service.py").read_text(
        encoding="utf-8"
    )

    assert 'id="answer_resolution"' in source
    assert 'label="Разрешение ответов"' in source
    assert 'title = "Разрешаем похожие ответы"' in source
    assert '"Черновики уже сохранены.' in source


def test_frontend_references_answer_resolution_step_key() -> None:
    source = Path("frontend/src/pages/knowledge/KnowledgePage.tsx").read_text(
        encoding="utf-8"
    )

    assert "ANSWER_RESOLUTION_STEP_ID = 'answer_resolution'" in source
