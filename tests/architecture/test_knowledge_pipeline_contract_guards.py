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
    assert "TASK_RESUME_KNOWLEDGE_PROCESSING" in source


def test_resume_task_is_dispatched_to_resume_handler() -> None:
    dispatcher = _read("src/infrastructure/queue/job_dispatcher.py")
    assert "TASK_RESUME_KNOWLEDGE_PROCESSING" in dispatcher
    assert "handle_resume_knowledge_processing" in dispatcher


def test_mutation_endpoints_require_expected_state_payload_contract() -> None:
    http_source = _read("src/interfaces/http/knowledge.py")
    assert "@router.post(\"/{document_id}/publish-ready\")" in http_source
    assert "@router.post(\"/{document_id}/retry-failed-batches\")" in http_source
    assert "@router.post(\"/{document_id}/retighten\")" in http_source
    assert "@router.post(\"/{document_id}/resume-processing\")" in http_source
    assert "@router.post(\"/{document_id}/cancel\")" in http_source
    assert http_source.count("KnowledgePipelineCommandRequestModel = Body(...)") >= 5


def test_processed_requires_retrieval_surface_rows_guard() -> None:
    source = _read("src/domain/project_plane/knowledge_document_pipeline.py")
    assert "has_retrieval_surface and document_status == \"processed\"" in source
