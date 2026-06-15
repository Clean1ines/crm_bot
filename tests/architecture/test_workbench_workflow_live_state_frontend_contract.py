from __future__ import annotations

from pathlib import Path


def test_workbench_workflow_live_state_endpoint_is_document_facing() -> None:
    source = Path("src/interfaces/http/knowledge.py").read_text(encoding="utf-8")

    assert '@router.get("/{document_id}/workflow-live-state")' in source
    assert "fetch_workbench_workflow_live_state" in source
    assert "workflow_run_id" in Path(
        "src/contexts/knowledge_workbench/observability/application/read_models/"
        "workbench_document_workflow_live_state.py"
    ).read_text(encoding="utf-8")


def test_workbench_workflow_live_state_does_not_trigger_publish_or_llm() -> None:
    source = Path(
        "src/interfaces/composition/faq_workbench_workflow_live_state.py"
    ).read_text(encoding="utf-8")
    forbidden = (
        "publish",
        "OpenAI",
        "Groq",
        "llm_executor",
        "mutate",
        "INSERT ",
        "UPDATE ",
        "DELETE ",
    )
    for marker in forbidden:
        assert marker not in source


def test_workbench_workflow_live_state_exposes_frontend_lanes_attempts_and_curation() -> (
    None
):
    source = Path(
        "src/contexts/knowledge_workbench/observability/application/read_models/"
        "workbench_document_workflow_live_state.py"
    ).read_text(encoding="utf-8")

    required = (
        "WorkbenchSectionLaneLiveView",
        "WorkbenchSectionQueueItemLiveView",
        "WorkbenchLlmAttemptLiveView",
        "WorkbenchRetryTimerLiveView",
        "WorkbenchCurationAvailabilityView",
        "WorkbenchWorkflowTimerLiveView",
        "WorkbenchWorkflowUsageLiveView",
    )
    for marker in required:
        assert marker in source
