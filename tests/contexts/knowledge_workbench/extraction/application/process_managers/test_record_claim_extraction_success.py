from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

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
from src.contexts.execution_runtime.domain.events.work_item_events import WorkItemCompleted
from src.contexts.execution_runtime.domain.state_machines.work_item_state_machine import WorkItemStateMachine
from src.contexts.execution_runtime.domain.value_objects.lease_token import LeaseToken
from src.contexts.execution_runtime.domain.value_objects.work_item_status import WorkItemStatus
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.execution_runtime.domain.value_objects.worker_ref import WorkerRef
from src.contexts.knowledge_workbench.extraction.application.ports.claim_extraction_work_item_unit_of_work_port import ClaimExtractionRuntimeEvent
from src.contexts.knowledge_workbench.extraction.application.process_managers.record_claim_extraction_success import (
    RecordClaimExtractionSuccess,
    RecordClaimExtractionSuccessCommand,
)
from src.contexts.llm_runtime.domain.entities.llm_attempt import LlmAttempt
from src.contexts.llm_runtime.domain.entities.llm_task import LlmTask
from src.contexts.llm_runtime.domain.events.llm_task_events import LlmTaskSucceeded
from src.contexts.llm_runtime.domain.value_objects.input_ref import LlmInputRef
from src.contexts.llm_runtime.domain.value_objects.llm_route import LlmRoute
from src.contexts.llm_runtime.domain.value_objects.llm_task_status import LlmTaskStatus
from src.contexts.llm_runtime.domain.value_objects.model_id import ModelId
from src.contexts.llm_runtime.domain.value_objects.output_contract_ref import OutputContractRef
from src.contexts.llm_runtime.domain.value_objects.prompt_version import PromptVersion
from src.contexts.llm_runtime.domain.value_objects.provider_account_ref import ProviderAccountRef
from src.contexts.llm_runtime.domain.value_objects.provider_id import ProviderId
from src.contexts.llm_runtime.domain.value_objects.token_usage import TokenUsage


@dataclass(slots=True)
class FakeClaimExtractionWorkItemUnitOfWork:
    saved_work_items: list[WorkItem] = field(default_factory=list)
    saved_work_item_attempts: list[WorkItemAttempt] = field(default_factory=list)
    saved_llm_tasks: list[LlmTask] = field(default_factory=list)
    saved_llm_attempts: list[LlmAttempt] = field(default_factory=list)
    saved_artifacts: list[PipelineArtifact] = field(default_factory=list)
    appended_events: list[ClaimExtractionRuntimeEvent] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    committed: bool = False
    rolled_back: bool = False
    fail_on_commit: bool = False
    fail_on_action: str | None = None

    def _record_action(self, action: str) -> None:
        self.actions.append(action)
        if self.fail_on_action == action:
            raise RuntimeError(f"{action} failed")

    def save_work_item(self, item: WorkItem) -> None:
        self._record_action("save_work_item")
        self.saved_work_items.append(item)

    def save_work_item_attempt(self, attempt: WorkItemAttempt) -> None:
        self._record_action("save_work_item_attempt")
        self.saved_work_item_attempts.append(attempt)

    def save_llm_task(self, task: LlmTask) -> None:
        self._record_action("save_llm_task")
        self.saved_llm_tasks.append(task)

    def save_llm_attempt(self, attempt: LlmAttempt) -> None:
        self._record_action("save_llm_attempt")
        self.saved_llm_attempts.append(attempt)

    def save_artifact(self, artifact: PipelineArtifact) -> None:
        self._record_action("save_artifact")
        self.saved_artifacts.append(artifact)

    def append_event(self, event: ClaimExtractionRuntimeEvent) -> None:
        self._record_action("append_event")
        self.appended_events.append(event)

    def commit(self) -> None:
        self.actions.append("commit")
        if self.fail_on_commit:
            raise RuntimeError("commit failed")
        self.committed = True

    def rollback(self) -> None:
        self.actions.append("rollback")
        self.rolled_back = True


def _now() -> datetime:
    return datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)


def _route() -> LlmRoute:
    return LlmRoute(
        provider_id=ProviderId("provider"),
        model_id=ModelId("model"),
        account_ref=ProviderAccountRef("account"),
    )


def _leased_work_item() -> WorkItem:
    now = _now()
    return WorkItemStateMachine.lease_ready(
        WorkItem(
            work_item_id="work-1",
            work_kind=WorkKind("knowledge_workbench.claim_extraction"),
        ),
        worker=WorkerRef("worker-1"),
        lease_token=LeaseToken("lease-1"),
        lease_expires_at=now + timedelta(seconds=30),
        now=now,
    )


def _work_item_attempt() -> WorkItemAttempt:
    return WorkItemAttempt(
        attempt_id="work-attempt-1",
        work_item_id="work-1",
        attempt_number=1,
        started_at=_now(),
        finished_at=_now(),
        outcome_status="completed",
    )


def _llm_task(status: LlmTaskStatus = LlmTaskStatus.SUCCEEDED) -> LlmTask:
    return LlmTask(
        task_id="llm-task-1",
        prompt_id="faq_claim_observations",
        prompt_version=PromptVersion("v1"),
        input_ref=LlmInputRef("source-unit-1"),
        output_contract_ref=OutputContractRef("claim_observations_json_v1"),
        status=status,
        selected_route=_route(),
    )


def _llm_attempt() -> LlmAttempt:
    return LlmAttempt(
        attempt_id="llm-attempt-1",
        task_id="llm-task-1",
        attempt_number=1,
        route=_route(),
        started_at=_now(),
        finished_at=_now(),
        usage=TokenUsage(input_tokens=10, output_tokens=5),
    )


def _prompt_a_provenance_payload() -> dict[str, object]:
    return {
        "workflow_run_id": "workflow-1",
        "stage_run_id": "stage-1",
        "source_unit_ref": "source-unit-1",
        "work_item_id": "work-1",
        "work_item_attempt_id": "work-attempt-1",
        "llm_task_id": "llm-task-1",
        "llm_attempt_id": "llm-attempt-1",
        "prompt_id": "faq_claim_observations",
        "prompt_version": "v1",
    }


def _raw_artifact() -> PipelineArtifact:
    payload = _prompt_a_provenance_payload()
    payload["raw_output"] = '{"claims": []}'
    return PipelineArtifact(
        artifact_ref=ArtifactRef("raw-artifact-1"),
        artifact_kind=ArtifactKind("knowledge_workbench.claim_observations.raw"),
        payload=ArtifactPayload(payload),
        status=ArtifactStatus.STORED,
        visibility=ArtifactVisibility.INTERNAL,
        retention_policy=RetentionPolicy.temporary(),
        lineage=ArtifactLineage(),
        created_at=_now(),
        updated_at=_now(),
    )


def _parsed_artifact(
    *,
    lineage: ArtifactLineage = ArtifactLineage(parent_refs=(ArtifactRef("raw-artifact-1"),)),
    raw_artifact_ref: str = "raw-artifact-1",
) -> PipelineArtifact:
    payload = _prompt_a_provenance_payload()
    payload["raw_artifact_ref"] = raw_artifact_ref
    payload["claims"] = ()
    return PipelineArtifact(
        artifact_ref=ArtifactRef("parsed-artifact-1"),
        artifact_kind=ArtifactKind("knowledge_workbench.claim_observations.parsed"),
        payload=ArtifactPayload(payload),
        status=ArtifactStatus.VALIDATED,
        visibility=ArtifactVisibility.INTERNAL,
        retention_policy=RetentionPolicy.temporary(),
        lineage=lineage,
        created_at=_now(),
        updated_at=_now(),
    )


def _command(
    *,
    llm_task: LlmTask | None = None,
    raw_output_artifact: PipelineArtifact | None = None,
    parsed_output_artifact: PipelineArtifact | None = None,
    occurred_at: datetime | None = None,
) -> RecordClaimExtractionSuccessCommand:
    return RecordClaimExtractionSuccessCommand(
        leased_work_item=_leased_work_item(),
        work_item_attempt=_work_item_attempt(),
        llm_task=llm_task or _llm_task(),
        llm_attempt=_llm_attempt(),
        raw_output_artifact=raw_output_artifact or _raw_artifact(),
        parsed_output_artifact=parsed_output_artifact or _parsed_artifact(),
        occurred_at=occurred_at or _now(),
    )


def test_record_claim_extraction_success_commits_runtime_write_set_atomically() -> None:
    unit_of_work = FakeClaimExtractionWorkItemUnitOfWork()

    result = RecordClaimExtractionSuccess(unit_of_work=unit_of_work).execute(_command())

    assert result.completed_work_item.status is WorkItemStatus.COMPLETED
    assert isinstance(result.work_item_event, WorkItemCompleted)
    assert isinstance(result.llm_event, LlmTaskSucceeded)
    assert unit_of_work.saved_work_items == [result.completed_work_item]
    assert unit_of_work.saved_work_item_attempts == [_work_item_attempt()]
    assert unit_of_work.saved_llm_tasks == [_llm_task()]
    assert unit_of_work.saved_llm_attempts == [_llm_attempt()]
    assert [artifact.artifact_ref.value for artifact in unit_of_work.saved_artifacts] == [
        "raw-artifact-1",
        "parsed-artifact-1",
    ]
    assert unit_of_work.appended_events == [
        result.work_item_event,
        result.llm_event,
        result.raw_artifact_event,
        result.parsed_artifact_event,
    ]
    assert unit_of_work.committed
    assert not unit_of_work.rolled_back


def test_record_claim_extraction_success_rejects_parsed_artifact_without_raw_parent_lineage() -> None:
    with pytest.raises(ValueError, match="sole parent"):
        _command(parsed_output_artifact=_parsed_artifact(lineage=ArtifactLineage()))


def test_record_claim_extraction_success_rejects_raw_ref_payload_lineage_mismatch() -> None:
    with pytest.raises(ValueError, match="raw artifact ref"):
        _command(parsed_output_artifact=_parsed_artifact(raw_artifact_ref="other-raw"))


def test_record_claim_extraction_success_rejects_arbitrary_artifact_payloads() -> None:
    bad_raw = PipelineArtifact(
        artifact_ref=ArtifactRef("raw-artifact-1"),
        artifact_kind=ArtifactKind("knowledge_workbench.claim_observations.raw"),
        payload=ArtifactPayload({"value": "not-provenance"}),
        status=ArtifactStatus.STORED,
        visibility=ArtifactVisibility.INTERNAL,
        retention_policy=RetentionPolicy.temporary(),
        lineage=ArtifactLineage(),
        created_at=_now(),
        updated_at=_now(),
    )

    with pytest.raises(ValueError):
        _command(raw_output_artifact=bad_raw)


def test_record_claim_extraction_success_rolls_back_when_commit_fails() -> None:
    unit_of_work = FakeClaimExtractionWorkItemUnitOfWork(fail_on_commit=True)

    with pytest.raises(RuntimeError, match="commit failed"):
        RecordClaimExtractionSuccess(unit_of_work=unit_of_work).execute(_command())

    assert not unit_of_work.committed
    assert unit_of_work.rolled_back
    assert unit_of_work.actions[-2:] == ["commit", "rollback"]


@pytest.mark.parametrize("fail_on_action", ("save_work_item", "append_event"))
def test_record_claim_extraction_success_rolls_back_when_save_or_append_fails(
    fail_on_action: str,
) -> None:
    unit_of_work = FakeClaimExtractionWorkItemUnitOfWork(fail_on_action=fail_on_action)

    with pytest.raises(RuntimeError, match=f"{fail_on_action} failed"):
        RecordClaimExtractionSuccess(unit_of_work=unit_of_work).execute(_command())

    assert not unit_of_work.committed
    assert unit_of_work.rolled_back
    assert fail_on_action in unit_of_work.actions
    assert unit_of_work.actions[-1] == "rollback"


def test_record_claim_extraction_success_requires_succeeded_llm_task() -> None:
    with pytest.raises(ValueError):
        _command(llm_task=_llm_task(status=LlmTaskStatus.READY))


def test_record_claim_extraction_success_requires_timezone_aware_occurred_at() -> None:
    with pytest.raises(ValueError):
        _command(occurred_at=datetime(2026, 6, 8, 12, 0))
