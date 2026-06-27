from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalCommandType,
)
from src.contexts.knowledge_workbench.application.sagas.trigger_claim_builder_capacity_drain_if_enabled import (
    DEFAULT_CLAIM_BUILDER_CAPACITY_DRAIN_WORKER_REF,
    TriggerClaimBuilderCapacityDrainIfEnabled,
    TriggerClaimBuilderCapacityDrainIfEnabledCommand,
)
from src.contexts.workflow_runtime.application.ports.workflow_runtime_unit_of_work_port import (
    WorkflowRuntimeUnitOfWorkPort,
)
from src.contexts.workflow_runtime.domain.entities.workflow_command import (
    WorkflowCommand,
    WorkflowCommandStatus,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_command_id import (
    WorkflowCommandId,
)


@dataclass(frozen=True, slots=True)
class HandleTriggerClaimBuilderCapacityDrainCommand:
    workflow_command: WorkflowCommand

    def __post_init__(self) -> None:
        if not isinstance(self.workflow_command, WorkflowCommand):
            raise TypeError("workflow_command must be WorkflowCommand")


@dataclass(frozen=True, slots=True)
class HandleTriggerClaimBuilderCapacityDrainResult:
    workflow_run_id: str
    skipped: bool
    skipped_reason: str | None
    drained_count: int
    execute_command_count: int
    provider_call_count: int
    completed_command_id: WorkflowCommandId

    def __post_init__(self) -> None:
        _require_non_empty_text(self.workflow_run_id, "workflow_run_id")
        if self.skipped_reason is not None:
            _require_non_empty_text(self.skipped_reason, "skipped_reason")
        _require_non_negative_int(self.drained_count, "drained_count")
        _require_non_negative_int(self.execute_command_count, "execute_command_count")
        _require_non_negative_int(self.provider_call_count, "provider_call_count")
        if not isinstance(self.completed_command_id, WorkflowCommandId):
            raise TypeError("completed_command_id must be WorkflowCommandId")


@dataclass(frozen=True, slots=True)
class HandleTriggerClaimBuilderCapacityDrainCommandHandler:
    async def execute(
        self,
        command: HandleTriggerClaimBuilderCapacityDrainCommand,
        *,
        trigger_claim_builder_capacity_drain_if_enabled: (
            TriggerClaimBuilderCapacityDrainIfEnabled
        ),
        workflow_unit_of_work: WorkflowRuntimeUnitOfWorkPort,
    ) -> HandleTriggerClaimBuilderCapacityDrainResult:
        workflow_command = command.workflow_command
        _validate_workflow_command(workflow_command)
        payload = workflow_command.payload
        workflow_run_id = _payload_text(
            payload,
            "workflow_run_id",
            fallback=workflow_command.workflow_run_id,
        )
        if workflow_run_id != workflow_command.workflow_run_id:
            raise ValueError("payload workflow_run_id must match workflow command")

        now = workflow_command.run_after or workflow_command.created_at
        worker_ref = (
            _payload_optional_text(payload, "worker_ref")
            or DEFAULT_CLAIM_BUILDER_CAPACITY_DRAIN_WORKER_REF
        )
        max_items = _payload_optional_positive_int(payload, "max_items") or 1

        drained_count = 0
        execute_command_count = 0
        provider_call_count = 0
        skipped_results: list[str] = []
        dispatched_window_count = 0

        for window_index, window in enumerate(_capacity_windows(payload)):
            result = await trigger_claim_builder_capacity_drain_if_enabled.execute(
                TriggerClaimBuilderCapacityDrainIfEnabledCommand(
                    workflow_run_id=workflow_run_id,
                    provider=window["provider"],
                    model_ref=window["model_ref"],
                    account_ref=window["account_ref"],
                    now=now,
                    worker_ref=f"{worker_ref}:window:{window_index}",
                    max_items=max_items,
                )
            )
            if result.skipped:
                if result.skipped_reason is not None:
                    skipped_results.append(result.skipped_reason)
                continue

            dispatched_window_count += 1
            drained_count += result.drained_count
            execute_command_count += result.execute_command_count
            provider_call_count += result.provider_call_count

        await workflow_unit_of_work.command_log.mark_command_completed(
            command_id=workflow_command.command_id,
            completed_at=now,
        )
        skipped = dispatched_window_count == 0
        return HandleTriggerClaimBuilderCapacityDrainResult(
            workflow_run_id=workflow_run_id,
            skipped=skipped,
            skipped_reason=skipped_results[0] if skipped_results and skipped else None,
            drained_count=drained_count,
            execute_command_count=execute_command_count,
            provider_call_count=provider_call_count,
            completed_command_id=workflow_command.command_id,
        )


def _capacity_windows(payload: Mapping[str, object]) -> tuple[dict[str, str], ...]:
    dispatch_preparation = payload.get("llm_dispatch_preparation")
    if not isinstance(dispatch_preparation, Mapping):
        return (
            {
                "provider": _payload_text(payload, "provider"),
                "model_ref": _payload_text(payload, "model_ref"),
                "account_ref": _payload_text(payload, "account_ref"),
            },
        )

    raw_windows = dispatch_preparation.get("account_capacities")
    if not isinstance(raw_windows, Sequence) or isinstance(raw_windows, str | bytes):
        raise ValueError("llm_dispatch_preparation account_capacities must be sequence")

    active_model_ref = dispatch_preparation.get("active_model_ref")
    windows: list[dict[str, str]] = []
    for raw_window in raw_windows:
        if not isinstance(raw_window, Mapping):
            continue
        if (
            isinstance(active_model_ref, str)
            and raw_window.get("model_ref") != active_model_ref
        ):
            continue
        windows.append(
            {
                "provider": _mapping_text(raw_window, "provider"),
                "model_ref": _mapping_text(raw_window, "model_ref"),
                "account_ref": _mapping_text(raw_window, "account_ref"),
            }
        )

    if not windows:
        raise ValueError("llm_dispatch_preparation must include account capacity")
    return tuple(windows)


def _mapping_text(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"capacity account must include {key}")
    return value


def _validate_workflow_command(workflow_command: WorkflowCommand) -> None:
    if (
        workflow_command.command_type
        != KnowledgeExtractionCanonicalCommandType.TRIGGER_CLAIM_BUILDER_CAPACITY_DRAIN.value
    ):
        raise ValueError(
            "workflow_command command_type must be TriggerClaimBuilderCapacityDrain"
        )
    if workflow_command.status is not WorkflowCommandStatus.PENDING:
        raise ValueError("workflow_command status must be PENDING")


def _payload_text(
    payload: Mapping[str, object],
    key: str,
    *,
    fallback: str | None = None,
) -> str:
    value = payload.get(key, fallback)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"workflow command payload must include {key}")
    return value


def _payload_optional_text(payload: Mapping[str, object], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"workflow command payload {key} must be text")
    return value


def _payload_optional_positive_int(
    payload: Mapping[str, object],
    key: str,
) -> int | None:
    value = payload.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"workflow command payload {key} must be positive int")
    return value


def _require_non_empty_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _require_non_negative_int(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be non-negative int")
