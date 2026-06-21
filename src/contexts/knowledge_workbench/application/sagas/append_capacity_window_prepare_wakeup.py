from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

import structlog

from src.contexts.capacity_runtime.application.ports.llm_attempt_capacity_observation_repository_port import (
    LlmAttemptCapacityObservation,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalCommandType,
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
from src.contexts.workflow_runtime.domain.value_objects.workflow_idempotency_key import (
    WorkflowIdempotencyKey,
)

from src.contexts.knowledge_workbench.application.sagas.capacity_window_workflow_events import (
    capacity_window_key,
)

LOGGER = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class CapacityWindowPrepareWakeup:
    provider: str
    account_ref: str
    model_ref: str
    run_after: datetime
    reset_at: datetime
    window_key: str
    command_id: WorkflowCommandId
    prepare_command_type: str
    wakeup_reason: str


async def append_capacity_window_prepare_wakeup(
    *,
    workflow_unit_of_work: WorkflowRuntimeUnitOfWorkPort,
    source_command: WorkflowCommand,
    workflow_run_id: str,
    prepare_command_type: KnowledgeExtractionCanonicalCommandType,
    capacity_observation: LlmAttemptCapacityObservation | None,
    occurred_at: datetime,
) -> CapacityWindowPrepareWakeup | None:
    """Append one durable prepare wakeup for the concrete provider/account/model.

    This is the missing bridge from provider-returned rate-limit reset time to
    workflow runtime. Work items remain queue candidates. The window owns time.
    """

    if capacity_observation is None:
        return None
    if capacity_observation.minute_reset_at is None:
        return None

    reset_at = capacity_observation.minute_reset_at
    run_after = reset_at
    if run_after <= occurred_at:
        run_after = occurred_at

    payload = _capacity_window_prepare_payload(
        source_payload=source_command.payload,
        workflow_run_id=workflow_run_id,
        capacity_observation=capacity_observation,
    )
    if not _has_scheduled_work_count(payload):
        LOGGER.warning(
            "knowledge_capacity_window_wakeup_skipped_missing_scheduled_count",
            workflow_run_id=workflow_run_id,
            provider=capacity_observation.provider,
            account_ref=capacity_observation.account_ref,
            model_ref=capacity_observation.model_ref,
            source_command_type=source_command.command_type,
            source_command_id=source_command.command_id.value,
        )
        return None

    idempotency_key = WorkflowIdempotencyKey(
        "capacity-window-prepare:"
        f"{workflow_run_id}:"
        f"{prepare_command_type.value}:"
        f"{capacity_observation.provider}:"
        f"{capacity_observation.account_ref}:"
        f"{capacity_observation.model_ref}:"
        f"{run_after.isoformat()}"
    )
    command_id = WorkflowCommandId(f"workflow-command:{idempotency_key.value}")

    await workflow_unit_of_work.command_log.append_pending_command(
        WorkflowCommand(
            command_id=command_id,
            command_type=prepare_command_type.value,
            workflow_run_id=workflow_run_id,
            idempotency_key=idempotency_key,
            payload=payload,
            status=WorkflowCommandStatus.PENDING,
            run_after=run_after,
            created_at=occurred_at,
            updated_at=occurred_at,
        )
    )

    LOGGER.info(
        "knowledge_capacity_window_prepare_wakeup_appended",
        workflow_run_id=workflow_run_id,
        command_type=prepare_command_type.value,
        command_id=command_id.value,
        provider=capacity_observation.provider,
        account_ref=capacity_observation.account_ref,
        model_ref=capacity_observation.model_ref,
        run_after=run_after.isoformat(),
        causation_command_id=source_command.command_id.value,
    )

    return CapacityWindowPrepareWakeup(
        provider=capacity_observation.provider,
        account_ref=capacity_observation.account_ref,
        model_ref=capacity_observation.model_ref,
        run_after=run_after,
        reset_at=reset_at,
        window_key=capacity_window_key(
            provider=capacity_observation.provider,
            account_ref=capacity_observation.account_ref,
            model_ref=capacity_observation.model_ref,
        ),
        command_id=command_id,
        prepare_command_type=prepare_command_type.value,
        wakeup_reason="provider_minute_reset",
    )


def _capacity_window_prepare_payload(
    *,
    source_payload: Mapping[str, object],
    workflow_run_id: str,
    capacity_observation: LlmAttemptCapacityObservation,
) -> dict[str, object]:
    payload = dict(source_payload)
    payload["workflow_run_id"] = workflow_run_id
    payload["active_model_ref"] = capacity_observation.model_ref
    payload["capacity_window_provider"] = capacity_observation.provider
    payload["capacity_window_provider_account_refs"] = [
        capacity_observation.account_ref,
    ]
    payload["capacity_window_model_ref"] = capacity_observation.model_ref

    dispatch_preparation = payload.get("llm_dispatch_preparation")
    if isinstance(dispatch_preparation, Mapping):
        updated_dispatch_preparation = dict(dispatch_preparation)
        updated_dispatch_preparation["active_model_ref"] = (
            capacity_observation.model_ref
        )
        # Critical: do not carry an old all-accounts seed into a window wakeup.
        # The generic prepare runner will rebuild seed capacity for the single
        # provider_account_refs override and then apply latest Groq observations.
        updated_dispatch_preparation.pop("account_capacities", None)
        payload["llm_dispatch_preparation"] = updated_dispatch_preparation

    return payload


def _has_scheduled_work_count(payload: Mapping[str, object]) -> bool:
    value = payload.get("scheduled_work_item_count")
    return isinstance(value, int) and not isinstance(value, bool) and value > 0
