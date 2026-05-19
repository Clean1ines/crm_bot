from pathlib import Path

from src.infrastructure.queue import job_types


ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_all_known_task_types_are_dispatched_or_explicitly_external() -> None:
    dispatcher_source = _read("src/infrastructure/queue/job_dispatcher.py")

    externally_dispatched = {
        job_types.TASK_NOTIFY_MANAGER,
        job_types.TASK_UPDATE_METRICS,
        job_types.TASK_AGGREGATE_METRICS,
        job_types.TASK_RUN_FULL_RAG_EVAL,
    }
    for task_type in job_types.KNOWN_TASK_TYPES:
        if task_type in externally_dispatched:
            continue
        assert task_type in dispatcher_source, (
            f"Known task type {task_type!r} is missing in dispatcher"
        )


def test_no_endpoint_enqueues_wrong_task_type_for_knowledge_pipeline_commands() -> None:
    http_source = _read("src/interfaces/http/knowledge.py")

    assert "publish_ready_task_type=TASK_PUBLISH_KNOWLEDGE_READY_ANSWERS" in http_source
    assert "retry_failed_batches_task_type=TASK_RETRY_KNOWLEDGE_FAILED_BATCHES" in http_source
    assert "retighten_task_type=TASK_RETIGHTEN_KNOWLEDGE_DOCUMENT" in http_source
    assert "resume_task_type=TASK_RESUME_KNOWLEDGE_PROCESSING" in http_source


def test_endpoint_command_matrix_exposes_resume_and_cancel_contract() -> None:
    http_source = _read("src/interfaces/http/knowledge.py")
    service_source = _read("src/application/services/knowledge_service.py")

    assert '@router.post("/{document_id}/resume-processing")' in http_source
    assert "resume_document_processing(" in service_source
    assert '@router.post("/{document_id}/cancel")' in http_source
    assert "cancel_document_processing(" in service_source
