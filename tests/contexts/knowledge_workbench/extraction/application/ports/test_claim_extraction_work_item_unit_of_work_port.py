from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from src.contexts.artifact_runtime.domain.entities.pipeline_artifact import (
    PipelineArtifact,
)
from src.contexts.artifact_runtime.domain.events.artifact_events import ArtifactStored
from src.contexts.artifact_runtime.domain.value_objects.artifact_kind import (
    ArtifactKind,
)
from src.contexts.artifact_runtime.domain.value_objects.artifact_lineage import (
    ArtifactLineage,
)
from src.contexts.artifact_runtime.domain.value_objects.artifact_payload import (
    ArtifactPayload,
)
from src.contexts.artifact_runtime.domain.value_objects.artifact_ref import ArtifactRef
from src.contexts.artifact_runtime.domain.value_objects.artifact_status import (
    ArtifactStatus,
)
from src.contexts.artifact_runtime.domain.value_objects.artifact_visibility import (
    ArtifactVisibility,
)
from src.contexts.artifact_runtime.domain.value_objects.retention_policy import (
    RetentionPolicy,
)
from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.entities.work_item_attempt import (
    WorkItemAttempt,
)
from src.contexts.execution_runtime.domain.events.work_item_events import (
    WorkItemCompleted,
)
from src.contexts.execution_runtime.domain.value_objects.work_item_status import (
    WorkItemStatus,
)
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.knowledge_workbench.extraction.application.ports.claim_extraction_work_item_unit_of_work_port import (
    ClaimExtractionRuntimeEvent,
    ClaimExtractionWorkItemUnitOfWorkPort,
)
from src.contexts.llm_runtime.domain.entities.llm_attempt import LlmAttempt
from src.contexts.llm_runtime.domain.entities.llm_task import LlmTask
from src.contexts.llm_runtime.domain.events.llm_task_events import LlmTaskSucceeded
from src.contexts.llm_runtime.domain.value_objects.input_ref import LlmInputRef
from src.contexts.llm_runtime.domain.value_objects.llm_route import LlmRoute
from src.contexts.llm_runtime.domain.value_objects.llm_task_status import LlmTaskStatus
from src.contexts.llm_runtime.domain.value_objects.model_id import ModelId
from src.contexts.llm_runtime.domain.value_objects.output_contract_ref import (
    OutputContractRef,
)
from src.contexts.llm_runtime.domain.value_objects.prompt_version import PromptVersion
from src.contexts.llm_runtime.domain.value_objects.provider_account_ref import (
    ProviderAccountRef,
)
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
    committed: bool = False
    rolled_back: bool = False

    def save_work_item(self, item: WorkItem) -> None:
        self.saved_work_items.append(item)

    def save_work_item_attempt(self, attempt: WorkItemAttempt) -> None:
        self.saved_work_item_attempts.append(attempt)

    def save_llm_task(self, task: LlmTask) -> None:
        self.saved_llm_tasks.append(task)

    def save_llm_attempt(self, attempt: LlmAttempt) -> None:
        self.saved_llm_attempts.append(attempt)

    def save_artifact(self, artifact: PipelineArtifact) -> None:
        self.saved_artifacts.append(artifact)

    def append_event(self, event: ClaimExtractionRuntimeEvent) -> None:
        self.appended_events.append(event)

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


def _now() -> datetime:
    return datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)


def _route() -> LlmRoute:
    return LlmRoute(
        provider_id=ProviderId("provider"),
        model_id=ModelId("model"),
        account_ref=ProviderAccountRef("account"),
    )


def _work_item() -> WorkItem:
    return WorkItem(
        work_item_id="work-1",
        work_kind=WorkKind("knowledge_workbench.claim_extraction"),
        status=WorkItemStatus.COMPLETED,
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


def _llm_task() -> LlmTask:
    return LlmTask(
        task_id="llm-task-1",
        prompt_id="faq_claim_observations",
        prompt_version=PromptVersion("v1"),
        input_ref=LlmInputRef("source-unit-1"),
        output_contract_ref=OutputContractRef("claim_observations_json_v1"),
        status=LlmTaskStatus.SUCCEEDED,
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


def _artifact() -> PipelineArtifact:
    return PipelineArtifact(
        artifact_ref=ArtifactRef("artifact-1"),
        artifact_kind=ArtifactKind("knowledge_workbench.claim_observations.raw"),
        payload=ArtifactPayload({"raw_text": '{"claims": []}'}),
        status=ArtifactStatus.STORED,
        visibility=ArtifactVisibility.INTERNAL,
        retention_policy=RetentionPolicy.temporary(),
        lineage=ArtifactLineage(),
        created_at=_now(),
        updated_at=_now(),
    )


def test_claim_extraction_uow_port_can_be_implemented_by_fake_transactional_facade() -> (
    None
):
    unit_of_work: ClaimExtractionWorkItemUnitOfWorkPort = (
        FakeClaimExtractionWorkItemUnitOfWork()
    )

    work_item = _work_item()
    work_item_attempt = _work_item_attempt()
    llm_task = _llm_task()
    llm_attempt = _llm_attempt()
    artifact = _artifact()

    unit_of_work.save_work_item(work_item)
    unit_of_work.save_work_item_attempt(work_item_attempt)
    unit_of_work.save_llm_task(llm_task)
    unit_of_work.save_llm_attempt(llm_attempt)
    unit_of_work.save_artifact(artifact)
    unit_of_work.append_event(
        WorkItemCompleted(work_item_id=work_item.work_item_id, occurred_at=_now()),
    )
    unit_of_work.append_event(
        LlmTaskSucceeded(task_id=llm_task.task_id, occurred_at=_now()),
    )
    unit_of_work.append_event(
        ArtifactStored(artifact_ref=artifact.artifact_ref, occurred_at=_now()),
    )
    unit_of_work.commit()

    assert isinstance(unit_of_work, FakeClaimExtractionWorkItemUnitOfWork)
    assert unit_of_work.saved_work_items == [work_item]
    assert unit_of_work.saved_work_item_attempts == [work_item_attempt]
    assert unit_of_work.saved_llm_tasks == [llm_task]
    assert unit_of_work.saved_llm_attempts == [llm_attempt]
    assert unit_of_work.saved_artifacts == [artifact]
    assert len(unit_of_work.appended_events) == 3
    assert unit_of_work.committed
    assert not unit_of_work.rolled_back
