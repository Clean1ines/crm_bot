from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import cast

from src.contexts.artifact_runtime.application.use_cases.persist_artifact import (
    PersistArtifact,
    PersistArtifactCommand,
)
from src.contexts.artifact_runtime.domain.value_objects.artifact_kind import (
    ArtifactKind,
)
from src.contexts.artifact_runtime.domain.value_objects.artifact_lineage import (
    ArtifactLineage,
)
from src.contexts.artifact_runtime.domain.value_objects.artifact_payload import (
    ArtifactPayload,
    JsonInputValue as ArtifactJsonInputValue,
)
from src.contexts.artifact_runtime.domain.value_objects.artifact_ref import ArtifactRef
from src.contexts.artifact_runtime.domain.value_objects.artifact_visibility import (
    ArtifactVisibility,
)
from src.contexts.artifact_runtime.domain.value_objects.retention_policy import (
    RetentionPolicy,
)
from src.contexts.execution_runtime.application.ports.work_item_attempt_dispatch_read_repository_port import (
    WorkItemAttemptDispatchForExecution,
)
from src.contexts.llm_runtime.application.ports.llm_dispatch_executor_port import (
    LlmDispatchExecutionResult,
    LlmDispatchExecutionStatus,
)
from src.contexts.llm_runtime.application.results.llm_dispatch_output_artifact_payload import (
    LLM_DISPATCH_OUTPUT_ARTIFACT_KIND_VALUE,
    LlmDispatchOutputArtifactPayload,
)


@dataclass(frozen=True, slots=True)
class PersistSuccessfulLlmDispatchArtifactsCommand:
    dispatch: WorkItemAttemptDispatchForExecution
    llm_result: LlmDispatchExecutionResult
    created_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.dispatch, WorkItemAttemptDispatchForExecution):
            raise TypeError("dispatch must be WorkItemAttemptDispatchForExecution")
        if not isinstance(self.llm_result, LlmDispatchExecutionResult):
            raise TypeError("llm_result must be LlmDispatchExecutionResult")
        if self.llm_result.status is not LlmDispatchExecutionStatus.SUCCEEDED:
            raise ValueError("llm_result must be succeeded")
        if not self.llm_result.output_payload:
            raise ValueError("llm_result.output_payload is required")
        _require_timezone_aware(self.created_at, field_name="created_at")


@dataclass(frozen=True, slots=True)
class PersistSuccessfulLlmDispatchArtifactsResult:
    artifacts: tuple[ArtifactRef, ...]


@dataclass(frozen=True, slots=True)
class PersistSuccessfulLlmDispatchArtifacts:
    persist_artifact: PersistArtifact

    async def execute(
        self,
        command: PersistSuccessfulLlmDispatchArtifactsCommand,
    ) -> PersistSuccessfulLlmDispatchArtifactsResult:
        artifact_ref = ArtifactRef(
            f"llm-dispatch-output:{command.dispatch.attempt_id}",
        )
        result = await self.persist_artifact.execute(
            PersistArtifactCommand(
                artifact_ref=artifact_ref,
                artifact_kind=ArtifactKind(LLM_DISPATCH_OUTPUT_ARTIFACT_KIND_VALUE),
                payload=ArtifactPayload(_artifact_payload(command)),
                visibility=ArtifactVisibility.INTERNAL,
                retention_policy=RetentionPolicy.temporary(),
                lineage=ArtifactLineage(),
                occurred_at=command.created_at,
            ),
        )
        return PersistSuccessfulLlmDispatchArtifactsResult(
            artifacts=(result.artifact.artifact_ref,),
        )


def _artifact_payload(
    command: PersistSuccessfulLlmDispatchArtifactsCommand,
) -> Mapping[str, ArtifactJsonInputValue]:
    output_payload = command.llm_result.output_payload
    if not output_payload:
        raise ValueError("llm_result.output_payload is required")

    payload = LlmDispatchOutputArtifactPayload(
        attempt_id=command.dispatch.attempt_id,
        work_item_id=command.dispatch.work_item_id,
        attempt_number=command.dispatch.attempt_number,
        worker_ref=command.dispatch.worker_ref,
        dispatch_payload=command.dispatch.dispatch_payload,
        output_payload=output_payload,
        finished_at=command.llm_result.finished_at.isoformat(),
    ).to_mapping()

    return cast(Mapping[str, ArtifactJsonInputValue], payload)


def _require_timezone_aware(value: datetime, *, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
