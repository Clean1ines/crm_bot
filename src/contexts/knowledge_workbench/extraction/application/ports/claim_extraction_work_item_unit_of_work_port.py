from __future__ import annotations

from typing import Protocol, TypeAlias

from src.contexts.artifact_runtime.domain.entities.pipeline_artifact import (
    PipelineArtifact,
)
from src.contexts.artifact_runtime.domain.events.artifact_events import (
    ArtifactExpired,
    ArtifactRejected,
    ArtifactStored,
    ArtifactSuperseded,
    ArtifactValidated,
)
from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.entities.work_item_attempt import (
    WorkItemAttempt,
)
from src.contexts.execution_runtime.domain.events.work_item_events import (
    WorkItemCancelled,
    WorkItemCompleted,
    WorkItemDeferred,
    WorkItemFailed,
    WorkItemLeaseExpired,
    WorkItemLeased,
    WorkItemSplitSuperseded,
    WorkItemUserActionRequired,
)
from src.contexts.llm_runtime.domain.entities.llm_attempt import LlmAttempt
from src.contexts.llm_runtime.domain.entities.llm_task import LlmTask
from src.contexts.llm_runtime.domain.events.llm_task_events import (
    LlmDailyLimitExhausted,
    LlmMinuteLimitHit,
    LlmTaskDeferred,
    LlmTaskFailed,
    LlmTaskSucceeded,
)


ClaimExtractionRuntimeEvent: TypeAlias = (
    WorkItemLeased
    | WorkItemCompleted
    | WorkItemDeferred
    | WorkItemFailed
    | WorkItemCancelled
    | WorkItemLeaseExpired
    | WorkItemSplitSuperseded
    | WorkItemUserActionRequired
    | LlmTaskSucceeded
    | LlmTaskDeferred
    | LlmTaskFailed
    | LlmDailyLimitExhausted
    | LlmMinuteLimitHit
    | ArtifactStored
    | ArtifactValidated
    | ArtifactRejected
    | ArtifactSuperseded
    | ArtifactExpired
)


class ClaimExtractionWorkItemUnitOfWorkPort(Protocol):
    """Cross-context transaction boundary for one extraction work item.

    This port is owned by Knowledge Workbench Extraction because Prompt A claim
    extraction is Workbench business orchestration over generic runtime contexts.

    Implementations may coordinate narrow repositories from execution_runtime,
    llm_runtime, artifact_runtime and knowledge_workbench/extraction, but the
    process manager must see only this use-case-scoped transactional facade.
    """

    def save_work_item(self, item: WorkItem) -> None:
        """Persist Execution Runtime WorkItem state."""

    def save_work_item_attempt(self, attempt: WorkItemAttempt) -> None:
        """Persist Execution Runtime WorkItemAttempt state."""

    def save_llm_task(self, task: LlmTask) -> None:
        """Persist LLM Runtime LlmTask state."""

    def save_llm_attempt(self, attempt: LlmAttempt) -> None:
        """Persist LLM Runtime LlmAttempt state."""

    def save_artifact(self, artifact: PipelineArtifact) -> None:
        """Persist Artifact Runtime PipelineArtifact state."""

    def append_event(self, event: ClaimExtractionRuntimeEvent) -> None:
        """Append durable event in the same transaction as state changes."""

    def commit(self) -> None:
        """Commit the cross-context transaction."""

    def rollback(self) -> None:
        """Rollback the cross-context transaction."""
