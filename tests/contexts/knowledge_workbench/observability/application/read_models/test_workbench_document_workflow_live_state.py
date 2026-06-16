from __future__ import annotations

from datetime import datetime, timezone

from src.contexts.knowledge_workbench.observability.application.read_models.workbench_document_workflow_live_state import (
    WorkbenchCurationAvailabilityView,
    WorkbenchDocumentWorkflowLiveState,
    WorkbenchLlmAttemptLiveView,
    WorkbenchRetryTimerLiveView,
    WorkbenchSectionLaneLiveView,
    WorkbenchSectionQueueItemLiveView,
    WorkbenchWorkflowActionView,
    WorkbenchWorkflowLiveState,
    WorkbenchWorkflowModelUsageLiveView,
    WorkbenchWorkflowStageLiveView,
    WorkbenchWorkflowTimerLiveView,
    WorkbenchWorkflowTimelineEntryLiveView,
    WorkbenchWorkflowUsageLiveView,
)


def _now() -> datetime:
    return datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)


def test_workflow_live_state_contract_contains_frontend_curation_workflow_id() -> None:
    state = WorkbenchDocumentWorkflowLiveState(
        document_id="source-document:project-1:abc",
        project_id="project-1",
        file_name="faq.md",
        document_status="processing",
        current_processing_run_id="run-1",
        workflow=WorkbenchWorkflowLiveState(
            workflow_run_id="workflow-1",
            source_document_ref="source-document:project-1:abc",
            workflow_status="RUNNING",
            current_phase="PROMPT_A_WORK_SCHEDULED",
            timer=WorkbenchWorkflowTimerLiveView(
                mode="running",
                active_elapsed_seconds=10,
                wall_elapsed_seconds=30,
                current_active_started_at=_now(),
                started_at=_now(),
                completed_at=None,
                is_live=True,
            ),
            usage=WorkbenchWorkflowUsageLiveView(
                total_prompt_tokens=100,
                total_completion_tokens=50,
                total_tokens=150,
                total_llm_calls=1,
                model_summaries=(
                    WorkbenchWorkflowModelUsageLiveView(
                        model_provider="groq",
                        model_name="llama",
                        call_count=1,
                        prompt_tokens=100,
                        completion_tokens=50,
                        total_tokens=150,
                        duration_ms_total=1234,
                    ),
                ),
            ),
            stages=(
                WorkbenchWorkflowStageLiveView(
                    id="prompt_a_claim_extraction",
                    label="Prompt A",
                    status="running",
                    current=1,
                    total=4,
                    message="Prompt A running",
                ),
            ),
            section_lanes=(
                WorkbenchSectionLaneLiveView(
                    lane_index=0,
                    lane_id="lane-0",
                    ready_count=1,
                    leased_count=1,
                    done_count=0,
                    failed_count=0,
                    waiting_count=0,
                    total_attempt_count=2,
                    max_attempt_count=2,
                    items=(
                        WorkbenchSectionQueueItemLiveView(
                            queue_item_id="queue-1",
                            section_id="section-1",
                            section_index=0,
                            section_key="s-1",
                            status="leased",
                            attempt_count=2,
                            lease_expires_at=_now(),
                            claimed_by_worker_id="worker-1",
                            error_kind=None,
                            retry_timer=WorkbenchRetryTimerLiveView(
                                retry_available_at=_now(),
                                seconds_until_retry=60,
                            ),
                        ),
                    ),
                ),
            ),
            llm_attempts=(
                WorkbenchLlmAttemptLiveView(
                    node_run_id="node-run-1",
                    section_id="section-1",
                    node_name="faq_claim_observations",
                    node_kind="llm",
                    status="completed",
                    started_at=_now(),
                    completed_at=_now(),
                    duration_ms=1234,
                    model_provider="groq",
                    model_name="llama",
                    prompt_tokens=100,
                    completion_tokens=50,
                    total_tokens=150,
                    error_kind=None,
                    error_message_user=None,
                ),
            ),
            timeline=(
                WorkbenchWorkflowTimelineEntryLiveView(
                    timeline_entry_id="timeline-1",
                    event_type="SourceUnitsCreated",
                    phase="SOURCE_INGESTION",
                    severity="info",
                    message="Source units created",
                    occurred_at=_now(),
                    source_ref="source-document:project-1:abc",
                    work_item_id=None,
                    attempt_id=None,
                ),
            ),
            curation=WorkbenchCurationAvailabilityView(
                available=True,
                reason_code="ready_to_open",
                workflow_run_id="workflow-1",
                workspace_ref=None,
                workspace_status=None,
                item_count=0,
                excluded_item_count=0,
            ),
            actions=(
                WorkbenchWorkflowActionView(
                    action_id="open_curation",
                    visible=True,
                    enabled=True,
                    reason_code=None,
                ),
            ),
        ),
    )

    payload = state.to_dict()

    assert payload["workflow"]["workflow_run_id"] == "workflow-1"
    assert payload["workflow"]["timer"]["is_live"] is True
    assert (
        payload["workflow"]["usage"]["model_summaries"][0]["model_provider"] == "groq"
    )
    assert payload["workflow"]["section_lanes"][0]["items"][0]["attempt_count"] == 2
    assert (
        payload["workflow"]["section_lanes"][0]["items"][0]["retry_timer"][
            "seconds_until_retry"
        ]
        == 60
    )
    assert payload["workflow"]["llm_attempts"][0]["duration_ms"] == 1234
    assert payload["workflow"]["timeline"][0]["event_type"] == "SourceUnitsCreated"
    assert payload["workflow"]["curation"]["available"] is True
