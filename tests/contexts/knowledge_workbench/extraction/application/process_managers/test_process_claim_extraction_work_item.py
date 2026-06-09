from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.contexts.artifact_runtime.domain.entities.pipeline_artifact import PipelineArtifact
from src.contexts.artifact_runtime.domain.value_objects.artifact_kind import ArtifactKind
from src.contexts.artifact_runtime.domain.value_objects.artifact_lineage import ArtifactLineage
from src.contexts.artifact_runtime.domain.value_objects.artifact_payload import ArtifactPayload
from src.contexts.artifact_runtime.domain.value_objects.artifact_ref import ArtifactRef
from src.contexts.artifact_runtime.domain.value_objects.artifact_status import ArtifactStatus
from src.contexts.artifact_runtime.domain.value_objects.artifact_visibility import ArtifactVisibility
from src.contexts.artifact_runtime.domain.value_objects.retention_policy import RetentionPolicy
from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.entities.work_item_attempt import WorkItemAttempt
from src.contexts.execution_runtime.domain.value_objects.lease_token import LeaseToken
from src.contexts.execution_runtime.domain.value_objects.wait_until import WaitUntil
from src.contexts.execution_runtime.domain.value_objects.work_item_status import WorkItemStatus
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.execution_runtime.domain.value_objects.worker_ref import WorkerRef
from src.contexts.knowledge_workbench.extraction.application.process_managers.process_claim_extraction_work_item import (
    ProcessClaimExtractionWorkItem,
    ProcessClaimExtractionWorkItemCommand,
)
from src.contexts.knowledge_workbench.extraction.application.process_managers.record_claim_extraction_daily_exhausted import RecordClaimExtractionDailyExhaustedCommand
from src.contexts.knowledge_workbench.extraction.application.process_managers.record_claim_extraction_deferred import RecordClaimExtractionDeferredCommand
from src.contexts.knowledge_workbench.extraction.application.process_managers.record_claim_extraction_failed import (
    ClaimExtractionFailureMode,
    RecordClaimExtractionFailedCommand,
)
from src.contexts.knowledge_workbench.extraction.application.process_managers.record_claim_extraction_split_required import RecordClaimExtractionSplitRequiredCommand
from src.contexts.knowledge_workbench.extraction.application.process_managers.record_claim_extraction_success import RecordClaimExtractionSuccessCommand
from src.contexts.llm_runtime.application.ports.llm_provider_input import (
    LlmProviderInput,
    LlmProviderMessage,
    LlmProviderMessageRole,
)
from src.contexts.llm_runtime.application.results.execute_llm_task_result import (
    ExecuteLlmTaskOutcome,
    ExecuteLlmTaskOutcomeKind,
)
from src.contexts.llm_runtime.application.use_cases.execute_llm_task import ExecuteLlmTaskCommand
from src.contexts.llm_runtime.domain.entities.llm_task import LlmTask
from src.contexts.llm_runtime.domain.value_objects.input_ref import LlmInputRef
from src.contexts.llm_runtime.domain.value_objects.llm_error_kind import LlmErrorKind
from src.contexts.llm_runtime.domain.value_objects.llm_route import LlmRoute
from src.contexts.llm_runtime.domain.value_objects.llm_task_status import LlmTaskStatus
from src.contexts.llm_runtime.domain.value_objects.model_id import ModelId
from src.contexts.llm_runtime.domain.value_objects.output_contract_ref import OutputContractRef
from src.contexts.llm_runtime.domain.value_objects.prompt_version import PromptVersion
from src.contexts.llm_runtime.domain.value_objects.provider_account_ref import ProviderAccountRef
from src.contexts.llm_runtime.domain.value_objects.provider_id import ProviderId
from src.contexts.llm_runtime.domain.value_objects.token_usage import TokenUsage


@dataclass(slots=True)
class FakeLlmExecutor:
    outcome: ExecuteLlmTaskOutcome
    calls: list[ExecuteLlmTaskCommand] = field(default_factory=list)

    def execute(self, command: ExecuteLlmTaskCommand) -> ExecuteLlmTaskOutcome:
        self.calls.append(command)
        return self.outcome


@dataclass(slots=True)
class FakeRecorder:
    label: str
    calls: list[object] = field(default_factory=list)

    def execute(self, command: object) -> object:
        self.calls.append(command)
        return f"{self.label}:recorded"


def _now() -> datetime:
    return datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)


def _route() -> LlmRoute:
    return LlmRoute(
        provider_id=ProviderId("provider-1"),
        model_id=ModelId("model-1"),
        account_ref=ProviderAccountRef("account-1"),
    )


def _provider_input() -> LlmProviderInput:
    return LlmProviderInput(
        messages=(
            LlmProviderMessage(
                role=LlmProviderMessageRole.USER,
                content="Extract claims.",
            ),
        ),
    )


def _work_item() -> WorkItem:
    return WorkItem(
        work_item_id="work-1",
        work_kind=WorkKind("knowledge_workbench.claim_extraction"),
        status=WorkItemStatus.LEASED,
        attempt_count=1,
        leased_by=WorkerRef("worker-1"),
        lease_token=LeaseToken("lease-1"),
        lease_expires_at=_now() + timedelta(seconds=30),
    )


def _work_item_attempt() -> WorkItemAttempt:
    return WorkItemAttempt(
        attempt_id="work-attempt-1",
        work_item_id="work-1",
        attempt_number=1,
        started_at=_now(),
    )


def _llm_task(
    *,
    status: LlmTaskStatus = LlmTaskStatus.READY,
    error_kind: LlmErrorKind | None = None,
    wait_until: datetime | None = None,
) -> LlmTask:
    return LlmTask(
        task_id="task-1",
        prompt_id="prompt-a",
        prompt_version=PromptVersion("v1"),
        input_ref=LlmInputRef("source-unit-1"),
        output_contract_ref=OutputContractRef("claim_observations_json_v1"),
        status=status,
        attempt_count=1,
        selected_route=_route() if status is LlmTaskStatus.RUNNING else None,
        wait_until=wait_until,
        last_error_kind=error_kind,
    )


def _prompt_a_provenance_payload() -> dict[str, object]:
    return {
        "workflow_run_id": "workflow-1",
        "stage_run_id": "stage-1",
        "source_unit_ref": "source-unit-1",
        "work_item_id": "work-1",
        "work_item_attempt_id": "work-attempt-1",
        "llm_task_id": "task-1",
        "llm_attempt_id": "llm-attempt-1",
        "prompt_id": "prompt-a",
        "prompt_version": "v1",
    }


def _artifact(ref: str, kind: str) -> PipelineArtifact:
    payload = _prompt_a_provenance_payload()
    if kind == "knowledge_workbench.claim_observations.raw":
        payload["raw_output"] = '{"claims": []}'
        lineage = ArtifactLineage()
    elif kind == "knowledge_workbench.claim_observations.parsed":
        payload["raw_artifact_ref"] = "raw-artifact-1"
        payload["claims"] = ()
        lineage = ArtifactLineage(parent_refs=(ArtifactRef("raw-artifact-1"),))
    else:
        payload = {"ok": True}
        lineage = ArtifactLineage()
    return PipelineArtifact(
        artifact_ref=ArtifactRef(ref),
        artifact_kind=ArtifactKind(kind),
        payload=ArtifactPayload(payload),
        status=ArtifactStatus.STORED,
        visibility=ArtifactVisibility.INTERNAL,
        retention_policy=RetentionPolicy.temporary(),
        lineage=lineage,
        created_at=_now(),
        updated_at=_now(),
    )


def _outcome(
    kind: ExecuteLlmTaskOutcomeKind,
    *,
    task: LlmTask | None = None,
    error_kind: LlmErrorKind | None = None,
    wait_until: datetime | None = None,
) -> ExecuteLlmTaskOutcome:
    return ExecuteLlmTaskOutcome(
        kind=kind,
        task=task or _llm_task(status=LlmTaskStatus.SUCCEEDED),
        raw_text='{"claims": []}'
        if kind is ExecuteLlmTaskOutcomeKind.SUCCEEDED
        else None,
        usage=TokenUsage(input_tokens=10, output_tokens=5)
        if kind is ExecuteLlmTaskOutcomeKind.SUCCEEDED
        else None,
        route=_route()
        if kind is ExecuteLlmTaskOutcomeKind.ROUTE_CHANGE_REQUIRED
        else None,
        wait_until=wait_until,
        error_kind=error_kind,
    )


@dataclass(slots=True)
class Harness:
    llm_executor: FakeLlmExecutor
    success: FakeRecorder
    deferred: FakeRecorder
    daily: FakeRecorder
    split: FakeRecorder
    failed: FakeRecorder
    process: ProcessClaimExtractionWorkItem


def _harness(outcome: ExecuteLlmTaskOutcome) -> Harness:
    llm_executor = FakeLlmExecutor(outcome=outcome)
    success = FakeRecorder("success")
    deferred = FakeRecorder("deferred")
    daily = FakeRecorder("daily")
    split = FakeRecorder("split")
    failed = FakeRecorder("failed")
    process = ProcessClaimExtractionWorkItem(
        llm_executor=llm_executor,
        success_recorder=success,
        deferred_recorder=deferred,
        daily_exhausted_recorder=daily,
        split_required_recorder=split,
        failed_recorder=failed,
    )
    return Harness(
        llm_executor=llm_executor,
        success=success,
        deferred=deferred,
        daily=daily,
        split=split,
        failed=failed,
        process=process,
    )


def _command(**overrides: object) -> ProcessClaimExtractionWorkItemCommand:
    values = {
        "leased_work_item": _work_item(),
        "work_item_attempt": _work_item_attempt(),
        "llm_task": _llm_task(),
        "route": _route(),
        "candidates": (),
        "provider_input": _provider_input(),
        "attempt_id": "llm-attempt-1",
        "attempt_number": 1,
        "started_at": _now(),
        "finished_at": _now() + timedelta(seconds=1),
        "occurred_at": _now() + timedelta(seconds=1),
        "raw_output_artifact": _artifact(
            "raw-artifact-1",
            "knowledge_workbench.claim_observations.raw",
        ),
        "parsed_output_artifact": _artifact(
            "parsed-artifact-1",
            "knowledge_workbench.claim_observations.parsed",
        ),
        "split_artifact": _artifact(
            "split-artifact-1",
            "knowledge_workbench.claim_extraction.split_required",
        ),
        "error_artifact": _artifact(
            "error-artifact-1",
            "knowledge_workbench.claim_extraction.error",
        ),
        "retry_next_attempt_at": WaitUntil(_now() + timedelta(seconds=30)),
    }
    values.update(overrides)
    return ProcessClaimExtractionWorkItemCommand(**values)


def test_success_dispatches_to_success_recorder() -> None:
    harness = _harness(_outcome(ExecuteLlmTaskOutcomeKind.SUCCEEDED))

    result = harness.process.execute(_command())

    assert result.dispatched_to == "success"
    assert result.llm_attempt.task_id == "task-1"
    assert result.llm_attempt.usage == TokenUsage(input_tokens=10, output_tokens=5)
    assert len(harness.llm_executor.calls) == 1
    assert len(harness.success.calls) == 1
    assert isinstance(harness.success.calls[0], RecordClaimExtractionSuccessCommand)
    assert not harness.deferred.calls
    assert not harness.daily.calls
    assert not harness.split.calls
    assert not harness.failed.calls


def test_success_rejects_arbitrary_prebuilt_artifacts_without_provenance() -> None:
    harness = _harness(_outcome(ExecuteLlmTaskOutcomeKind.SUCCEEDED))
    arbitrary_raw = PipelineArtifact(
        artifact_ref=ArtifactRef("raw-artifact-1"),
        artifact_kind=ArtifactKind("knowledge_workbench.claim_observations.raw"),
        payload=ArtifactPayload({"ok": True}),
        status=ArtifactStatus.STORED,
        visibility=ArtifactVisibility.INTERNAL,
        retention_policy=RetentionPolicy.temporary(),
        lineage=ArtifactLineage(),
        created_at=_now(),
        updated_at=_now(),
    )

    with pytest.raises(ValueError):
        harness.process.execute(_command(raw_output_artifact=arbitrary_raw))

    assert not harness.success.calls


def test_deferred_dispatches_to_deferred_recorder() -> None:
    wait_until = _now() + timedelta(seconds=60)
    task = _llm_task(
        status=LlmTaskStatus.DEFERRED,
        error_kind=LlmErrorKind.MINUTE_LIMIT,
        wait_until=wait_until,
    )
    harness = _harness(
        _outcome(
            ExecuteLlmTaskOutcomeKind.DEFERRED,
            task=task,
            error_kind=LlmErrorKind.MINUTE_LIMIT,
            wait_until=wait_until,
        ),
    )

    result = harness.process.execute(_command())

    assert result.dispatched_to == "deferred"
    assert result.llm_attempt.error_kind is LlmErrorKind.MINUTE_LIMIT
    assert len(harness.deferred.calls) == 1
    assert isinstance(harness.deferred.calls[0], RecordClaimExtractionDeferredCommand)
    assert not harness.success.calls
    assert not harness.daily.calls
    assert not harness.split.calls
    assert not harness.failed.calls


def test_daily_exhausted_dispatches_to_daily_recorder() -> None:
    task = _llm_task(
        status=LlmTaskStatus.RETRYABLE_FAILED,
        error_kind=LlmErrorKind.DAILY_LIMIT,
    )
    harness = _harness(
        _outcome(
            ExecuteLlmTaskOutcomeKind.DAILY_EXHAUSTED,
            task=task,
            error_kind=LlmErrorKind.DAILY_LIMIT,
        ),
    )

    result = harness.process.execute(_command())

    assert result.dispatched_to == "daily_exhausted"
    assert len(harness.daily.calls) == 1
    assert isinstance(harness.daily.calls[0], RecordClaimExtractionDailyExhaustedCommand)
    assert not harness.success.calls
    assert not harness.deferred.calls
    assert not harness.split.calls
    assert not harness.failed.calls


def test_split_required_dispatches_to_split_recorder() -> None:
    task = _llm_task(
        status=LlmTaskStatus.TERMINAL_FAILED,
        error_kind=LlmErrorKind.REQUEST_TOO_LARGE,
    )
    harness = _harness(
        _outcome(
            ExecuteLlmTaskOutcomeKind.SPLIT_REQUIRED,
            task=task,
            error_kind=LlmErrorKind.REQUEST_TOO_LARGE,
        ),
    )

    result = harness.process.execute(_command())

    assert result.dispatched_to == "split_required"
    assert len(harness.split.calls) == 1
    assert isinstance(harness.split.calls[0], RecordClaimExtractionSplitRequiredCommand)
    assert not harness.success.calls
    assert not harness.deferred.calls
    assert not harness.daily.calls
    assert not harness.failed.calls


def test_terminal_failure_dispatches_to_failed_recorder() -> None:
    task = _llm_task(
        status=LlmTaskStatus.TERMINAL_FAILED,
        error_kind=LlmErrorKind.AUTH_ERROR,
    )
    harness = _harness(
        _outcome(
            ExecuteLlmTaskOutcomeKind.TERMINAL_FAILED,
            task=task,
            error_kind=LlmErrorKind.AUTH_ERROR,
        ),
    )

    result = harness.process.execute(_command())

    assert result.dispatched_to == "terminal_failed"
    assert len(harness.failed.calls) == 1
    failed_command = harness.failed.calls[0]
    assert isinstance(failed_command, RecordClaimExtractionFailedCommand)
    assert failed_command.mode is ClaimExtractionFailureMode.TERMINAL
    assert not harness.success.calls
    assert not harness.deferred.calls
    assert not harness.daily.calls
    assert not harness.split.calls


def test_retry_required_dispatches_to_failed_recorder_as_retryable() -> None:
    task = _llm_task(
        status=LlmTaskStatus.RETRYABLE_FAILED,
        error_kind=LlmErrorKind.VALIDATION_FAILED,
    )
    harness = _harness(
        _outcome(
            ExecuteLlmTaskOutcomeKind.RETRY_REQUIRED,
            task=task,
            error_kind=LlmErrorKind.VALIDATION_FAILED,
        ),
    )

    result = harness.process.execute(_command())

    assert result.dispatched_to == "retryable_failed"
    failed_command = harness.failed.calls[0]
    assert isinstance(failed_command, RecordClaimExtractionFailedCommand)
    assert failed_command.mode is ClaimExtractionFailureMode.RETRYABLE
    assert failed_command.next_attempt_at == WaitUntil(_now() + timedelta(seconds=30))


def test_route_change_required_dispatches_to_failed_recorder_as_retryable() -> None:
    task = _llm_task(
        status=LlmTaskStatus.RETRYABLE_FAILED,
        error_kind=LlmErrorKind.MINUTE_LIMIT,
    )
    harness = _harness(
        _outcome(
            ExecuteLlmTaskOutcomeKind.ROUTE_CHANGE_REQUIRED,
            task=task,
            error_kind=LlmErrorKind.MINUTE_LIMIT,
        ),
    )

    result = harness.process.execute(_command())

    assert result.dispatched_to == "retryable_failed"
    assert isinstance(harness.failed.calls[0], RecordClaimExtractionFailedCommand)


def test_confirm_empty_output_dispatches_to_failed_recorder_as_retryable() -> None:
    task = _llm_task(
        status=LlmTaskStatus.RETRYABLE_FAILED,
        error_kind=LlmErrorKind.EMPTY_OUTPUT,
    )
    harness = _harness(
        _outcome(
            ExecuteLlmTaskOutcomeKind.CONFIRM_EMPTY_OUTPUT_REQUIRED,
            task=task,
            error_kind=LlmErrorKind.EMPTY_OUTPUT,
        ),
    )

    result = harness.process.execute(_command())

    assert result.dispatched_to == "retryable_failed"
    assert isinstance(harness.failed.calls[0], RecordClaimExtractionFailedCommand)


def test_retryable_outcome_requires_next_attempt_at() -> None:
    task = _llm_task(
        status=LlmTaskStatus.RETRYABLE_FAILED,
        error_kind=LlmErrorKind.VALIDATION_FAILED,
    )
    harness = _harness(
        _outcome(
            ExecuteLlmTaskOutcomeKind.RETRY_REQUIRED,
            task=task,
            error_kind=LlmErrorKind.VALIDATION_FAILED,
        ),
    )

    with pytest.raises(ValueError, match="requires retry_next_attempt_at"):
        harness.process.execute(_command(retry_next_attempt_at=None))


def test_success_requires_raw_and_parsed_artifacts() -> None:
    harness = _harness(_outcome(ExecuteLlmTaskOutcomeKind.SUCCEEDED))

    with pytest.raises(ValueError, match="raw_output_artifact"):
        harness.process.execute(_command(raw_output_artifact=None))

    with pytest.raises(ValueError, match="parsed_output_artifact"):
        harness.process.execute(_command(parsed_output_artifact=None))


def test_split_required_requires_split_artifact() -> None:
    task = _llm_task(
        status=LlmTaskStatus.TERMINAL_FAILED,
        error_kind=LlmErrorKind.REQUEST_TOO_LARGE,
    )
    harness = _harness(
        _outcome(
            ExecuteLlmTaskOutcomeKind.SPLIT_REQUIRED,
            task=task,
            error_kind=LlmErrorKind.REQUEST_TOO_LARGE,
        ),
    )

    with pytest.raises(ValueError, match="split_artifact"):
        harness.process.execute(_command(split_artifact=None))


def test_process_command_requires_timezone_aware_timestamps() -> None:
    with pytest.raises(ValueError, match="started_at must be timezone-aware"):
        _command(started_at=datetime(2026, 6, 8, 12, 0))

    with pytest.raises(ValueError, match="finished_at must be >= started_at"):
        _command(finished_at=_now() - timedelta(seconds=1))


def test_process_claim_extraction_source_does_not_import_provider_db_or_legacy_paths() -> None:
    source = Path(
        "src/contexts/knowledge_workbench/extraction/application/process_managers/"
        "process_claim_extraction_work_item.py",
    ).read_text(encoding="utf-8")

    forbidden = (
        "src.contexts.llm_runtime.infrastructure",
        "src.infrastructure.",
        "src.application.",
        "src.domain.project_plane.",
        "src.interfaces.",
        "knowledge_workbench_section_batch_queue_items",
        "knowledge_workbench_parallel_section_batch_plans",
        "ProcessingNodeRun",
        "ProcessingNodeArtifact",
        "SectionBatchQueueItem",
        "FaqWorkbench",
        ".status =",
        "asyncpg",
        "connection.execute",
        "fetchrow",
        "type: ignore",
    )

    offenders = [marker for marker in forbidden if marker in source]
    assert not offenders
