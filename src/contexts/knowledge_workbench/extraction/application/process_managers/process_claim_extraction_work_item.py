from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from src.contexts.artifact_runtime.domain.entities.pipeline_artifact import (
    PipelineArtifact,
)
from src.contexts.artifact_runtime.domain.value_objects.artifact_payload import (
    JsonInputValue,
)
from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.entities.work_item_attempt import (
    WorkItemAttempt,
)
from src.contexts.execution_runtime.domain.value_objects.wait_until import WaitUntil
from src.contexts.knowledge_workbench.extraction.application.policies.claim_extraction_artifact_provenance import (
    ClaimExtractionArtifactProvenance,
)
from src.contexts.knowledge_workbench.extraction.application.policies.claim_extraction_prompt_a_artifact_factory import (
    ClaimExtractionPromptAArtifactFactory,
)
from src.contexts.knowledge_workbench.extraction.application.process_managers.record_claim_extraction_daily_exhausted import (
    RecordClaimExtractionDailyExhaustedCommand,
)
from src.contexts.knowledge_workbench.extraction.application.process_managers.record_claim_extraction_deferred import (
    RecordClaimExtractionDeferredCommand,
)
from src.contexts.knowledge_workbench.extraction.application.process_managers.record_claim_extraction_failed import (
    ClaimExtractionFailureMode,
    RecordClaimExtractionFailedCommand,
)
from src.contexts.knowledge_workbench.extraction.application.process_managers.record_claim_extraction_split_required import (
    RecordClaimExtractionSplitRequiredCommand,
)
from src.contexts.knowledge_workbench.extraction.application.process_managers.record_claim_extraction_success import (
    RecordClaimExtractionSuccessCommand,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_ref import (
    SourceUnitRef,
)
from src.contexts.llm_runtime.application.policies.llm_route_planning_policy import (
    LlmRouteCandidate,
)
from src.contexts.llm_runtime.application.ports.llm_provider_input import (
    LlmProviderInput,
)
from src.contexts.llm_runtime.application.results.execute_llm_task_result import (
    ExecuteLlmTaskOutcome,
    ExecuteLlmTaskOutcomeKind,
)
from src.contexts.llm_runtime.application.use_cases.execute_llm_task import (
    ExecuteLlmTaskCommand,
)
from src.contexts.llm_runtime.domain.entities.llm_attempt import LlmAttempt
from src.contexts.llm_runtime.domain.entities.llm_task import LlmTask
from src.contexts.llm_runtime.domain.value_objects.llm_route import LlmRoute


class ClaimExtractionLlmExecutorPort(Protocol):
    def execute(self, command: ExecuteLlmTaskCommand) -> ExecuteLlmTaskOutcome: ...


class ClaimExtractionOutcomeRecorderPort(Protocol):
    def execute(self, command: object) -> object: ...


@dataclass(frozen=True, slots=True)
class ProcessClaimExtractionWorkItemCommand:
    leased_work_item: WorkItem
    work_item_attempt: WorkItemAttempt
    llm_task: LlmTask
    route: LlmRoute
    candidates: tuple[LlmRouteCandidate, ...]
    provider_input: LlmProviderInput
    attempt_id: str
    attempt_number: int
    started_at: datetime
    finished_at: datetime
    occurred_at: datetime
    workflow_run_id: str
    stage_run_id: str
    source_unit_ref: SourceUnitRef
    parsed_claims_payload: tuple[Mapping[str, JsonInputValue], ...]
    split_artifact: PipelineArtifact | None = None
    error_artifact: PipelineArtifact | None = None
    retry_next_attempt_at: WaitUntil | None = None

    def __post_init__(self) -> None:
        _require_non_empty_string(self.attempt_id, "attempt_id")
        _require_non_empty_string(self.workflow_run_id, "workflow_run_id")
        _require_non_empty_string(self.stage_run_id, "stage_run_id")
        if self.attempt_number < 1:
            raise ValueError("attempt_number must be >= 1")
        _require_timezone_aware(self.started_at, "started_at")
        _require_timezone_aware(self.finished_at, "finished_at")
        _require_timezone_aware(self.occurred_at, "occurred_at")
        if self.finished_at < self.started_at:
            raise ValueError("finished_at must be >= started_at")
        _require_parsed_claims_payload(self.parsed_claims_payload)


@dataclass(frozen=True, slots=True)
class ProcessClaimExtractionWorkItemResult:
    outcome: ExecuteLlmTaskOutcome
    llm_attempt: LlmAttempt
    dispatched_to: str
    recorder_result: object


class ProcessClaimExtractionWorkItem:
    """Execute one leased claim-extraction work item and delegate outcome recording."""

    def __init__(
        self,
        *,
        llm_executor: ClaimExtractionLlmExecutorPort,
        success_recorder: ClaimExtractionOutcomeRecorderPort,
        deferred_recorder: ClaimExtractionOutcomeRecorderPort,
        daily_exhausted_recorder: ClaimExtractionOutcomeRecorderPort,
        split_required_recorder: ClaimExtractionOutcomeRecorderPort,
        failed_recorder: ClaimExtractionOutcomeRecorderPort,
        artifact_factory: ClaimExtractionPromptAArtifactFactory | None = None,
    ) -> None:
        self._llm_executor = llm_executor
        self._success_recorder = success_recorder
        self._deferred_recorder = deferred_recorder
        self._daily_exhausted_recorder = daily_exhausted_recorder
        self._split_required_recorder = split_required_recorder
        self._failed_recorder = failed_recorder
        self._artifact_factory = artifact_factory or ClaimExtractionPromptAArtifactFactory()

    def execute(
        self,
        command: ProcessClaimExtractionWorkItemCommand,
    ) -> ProcessClaimExtractionWorkItemResult:
        outcome = self._llm_executor.execute(
            ExecuteLlmTaskCommand(
                task=command.llm_task,
                route=command.route,
                candidates=command.candidates,
                provider_input=command.provider_input,
            ),
        )

        llm_attempt = LlmAttempt(
            attempt_id=command.attempt_id,
            task_id=outcome.task.task_id,
            attempt_number=command.attempt_number,
            route=command.route,
            started_at=command.started_at,
            finished_at=command.finished_at,
            usage=outcome.usage,
            error_kind=outcome.error_kind,
        )

        recorder_result, dispatched_to = self._dispatch_outcome(
            command=command,
            outcome=outcome,
            llm_attempt=llm_attempt,
        )

        return ProcessClaimExtractionWorkItemResult(
            outcome=outcome,
            llm_attempt=llm_attempt,
            dispatched_to=dispatched_to,
            recorder_result=recorder_result,
        )

    def _dispatch_outcome(
        self,
        *,
        command: ProcessClaimExtractionWorkItemCommand,
        outcome: ExecuteLlmTaskOutcome,
        llm_attempt: LlmAttempt,
    ) -> tuple[object, str]:
        if outcome.kind is ExecuteLlmTaskOutcomeKind.SUCCEEDED:
            raw_text = outcome.raw_text
            if raw_text is None:
                raise ValueError("SUCCEEDED outcome must carry raw_text")

            provenance = ClaimExtractionArtifactProvenance(
                workflow_run_id=command.workflow_run_id,
                stage_run_id=command.stage_run_id,
                source_unit_ref=command.source_unit_ref,
                work_item_id=command.leased_work_item.work_item_id,
                work_item_attempt_id=command.work_item_attempt.attempt_id,
                llm_task_id=outcome.task.task_id,
                llm_attempt_id=llm_attempt.attempt_id,
                prompt_id=outcome.task.prompt_id,
                prompt_version=outcome.task.prompt_version.value,
            )
            artifacts = self._artifact_factory.build(
                provenance=provenance,
                raw_output=raw_text,
                parsed_claims_payload=command.parsed_claims_payload,
                created_at=command.occurred_at,
                updated_at=command.occurred_at,
            )

            return (
                self._success_recorder.execute(
                    RecordClaimExtractionSuccessCommand(
                        leased_work_item=command.leased_work_item,
                        work_item_attempt=command.work_item_attempt,
                        llm_task=outcome.task,
                        llm_attempt=llm_attempt,
                        raw_output_artifact=artifacts.raw_output_artifact,
                        parsed_output_artifact=artifacts.parsed_output_artifact,
                        occurred_at=command.occurred_at,
                    ),
                ),
                "success",
            )

        if outcome.kind is ExecuteLlmTaskOutcomeKind.DEFERRED:
            return (
                self._deferred_recorder.execute(
                    RecordClaimExtractionDeferredCommand(
                        leased_work_item=command.leased_work_item,
                        work_item_attempt=command.work_item_attempt,
                        llm_task=outcome.task,
                        llm_attempt=llm_attempt,
                        occurred_at=command.occurred_at,
                        error_artifact=command.error_artifact,
                    ),
                ),
                "deferred",
            )

        if outcome.kind is ExecuteLlmTaskOutcomeKind.DAILY_EXHAUSTED:
            return (
                self._daily_exhausted_recorder.execute(
                    RecordClaimExtractionDailyExhaustedCommand(
                        leased_work_item=command.leased_work_item,
                        work_item_attempt=command.work_item_attempt,
                        llm_task=outcome.task,
                        llm_attempt=llm_attempt,
                        occurred_at=command.occurred_at,
                        error_artifact=command.error_artifact,
                    ),
                ),
                "daily_exhausted",
            )

        if outcome.kind is ExecuteLlmTaskOutcomeKind.SPLIT_REQUIRED:
            split_artifact = _require_artifact(
                command.split_artifact,
                "split_artifact",
                outcome.kind,
            )
            return (
                self._split_required_recorder.execute(
                    RecordClaimExtractionSplitRequiredCommand(
                        leased_work_item=command.leased_work_item,
                        work_item_attempt=command.work_item_attempt,
                        llm_task=outcome.task,
                        llm_attempt=llm_attempt,
                        split_artifact=split_artifact,
                        occurred_at=command.occurred_at,
                    ),
                ),
                "split_required",
            )

        if outcome.kind is ExecuteLlmTaskOutcomeKind.TERMINAL_FAILED:
            return (
                self._failed_recorder.execute(
                    RecordClaimExtractionFailedCommand(
                        leased_work_item=command.leased_work_item,
                        work_item_attempt=command.work_item_attempt,
                        llm_task=outcome.task,
                        llm_attempt=llm_attempt,
                        mode=ClaimExtractionFailureMode.TERMINAL,
                        occurred_at=command.occurred_at,
                        error_artifact=command.error_artifact,
                    ),
                ),
                "terminal_failed",
            )

        if outcome.kind in {
            ExecuteLlmTaskOutcomeKind.RETRY_REQUIRED,
            ExecuteLlmTaskOutcomeKind.ROUTE_CHANGE_REQUIRED,
            ExecuteLlmTaskOutcomeKind.CONFIRM_EMPTY_OUTPUT_REQUIRED,
        }:
            if command.retry_next_attempt_at is None:
                raise ValueError(
                    f"{outcome.kind.value} outcome requires retry_next_attempt_at",
                )
            return (
                self._failed_recorder.execute(
                    RecordClaimExtractionFailedCommand(
                        leased_work_item=command.leased_work_item,
                        work_item_attempt=command.work_item_attempt,
                        llm_task=outcome.task,
                        llm_attempt=llm_attempt,
                        mode=ClaimExtractionFailureMode.RETRYABLE,
                        occurred_at=command.occurred_at,
                        next_attempt_at=command.retry_next_attempt_at,
                        error_artifact=command.error_artifact,
                    ),
                ),
                "retryable_failed",
            )

        raise ValueError(f"Unsupported claim extraction outcome: {outcome.kind.value}")


def _require_non_empty_string(value: str, field_name: str) -> None:
    if not value or not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _require_timezone_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


def _require_parsed_claims_payload(
    parsed_claims_payload: tuple[Mapping[str, JsonInputValue], ...],
) -> None:
    if not isinstance(parsed_claims_payload, tuple):
        raise ValueError("parsed_claims_payload must be a tuple")
    for claim_payload in parsed_claims_payload:
        if not isinstance(claim_payload, Mapping):
            raise ValueError("parsed_claims_payload items must be mappings")


def _require_artifact(
    artifact: PipelineArtifact | None,
    field_name: str,
    outcome_kind: ExecuteLlmTaskOutcomeKind,
) -> PipelineArtifact:
    if artifact is None:
        raise ValueError(f"{outcome_kind.value} outcome requires {field_name}")
    return artifact
