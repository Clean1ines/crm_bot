from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_publish_ready_label_contains_without_resolution_when_pending() -> None:
    source = _read("src/domain/project_plane/knowledge_document_pipeline.py")
    assert "publish_raw_drafts_without_resolution" in source
    assert "Опубликовать черновики без уплотнения" in source


def test_no_endpoint_enqueues_wrong_task_type() -> None:
    source = _read("src/interfaces/http/knowledge.py")
    assert "TASK_PUBLISH_KNOWLEDGE_READY_ANSWERS" in source
    assert "TASK_RETRY_KNOWLEDGE_FAILED_BATCHES" in source
    assert "TASK_RETIGHTEN_KNOWLEDGE_DOCUMENT" in source


def test_processed_requires_retrieval_surface_rows_guard() -> None:
    source = _read("src/domain/project_plane/knowledge_document_pipeline.py")
    assert "has_retrieval_surface and document_status == \"processed\"" in source
