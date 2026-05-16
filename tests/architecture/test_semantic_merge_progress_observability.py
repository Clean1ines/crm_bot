from __future__ import annotations

from pathlib import Path


def test_semantic_merge_progress_metrics_are_persisted_before_publication() -> None:
    source = Path("src/application/services/knowledge_ingestion_service.py").read_text(
        encoding="utf-8"
    )

    progress_index = source.index("async def persist_semantic_merge_progress")
    tighten_index = source.index("await _tighten_compiled_entries_with_semantic_merge")
    publish_index = source.index(
        "canonical_entries = _canonical_entries_from_preprocessing_result",
        tighten_index,
    )
    progress_slice = source[progress_index:publish_index]

    assert progress_index < tighten_index < publish_index
    assert '"stage": "semantic_merge_tightening"' in progress_slice
    assert (
        '"processed_group_count"'
        in source[
            source.index(
                "async def _tighten_compiled_entries_with_semantic_merge"
            ) : publish_index
        ]
    )
    assert "on_progress=persist_semantic_merge_progress" in progress_slice


def test_processing_report_exposes_semantic_merge_tightening_step() -> None:
    source = Path("src/application/services/knowledge_service.py").read_text(
        encoding="utf-8"
    )

    assert 'id="semantic_merge_tightening"' in source
    assert 'label="Уплотнение смысловых дублей"' in source
    assert 'title = "Уплотняем похожие ответы"' in source
    assert '"Черновики уже сохранены.' in source


def test_frontend_references_semantic_merge_tightening_step_key() -> None:
    source = Path("frontend/src/pages/knowledge/KnowledgePage.tsx").read_text(
        encoding="utf-8"
    )

    assert "SEMANTIC_MERGE_TIGHTENING_STEP_ID = 'semantic_merge_tightening'" in source
