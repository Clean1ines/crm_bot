from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalCommandType,
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


DEFAULT_CLAIM_BUILDER_CAPACITY_DRAIN_WORKER_REF = "claim-builder-capacity-drain"


@dataclass(frozen=True, slots=True)
class BuildClaimBuilderCapacityDrainTriggerCommand:
    workflow_run_id: str
    source_document_ref: str | None
    llm_dispatch_preparation: Mapping[str, object]
    max_items: int
    run_after: datetime
    occurred_at: datetime
    worker_ref: str = DEFAULT_CLAIM_BUILDER_CAPACITY_DRAIN_WORKER_REF
    context_payload: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        _require_non_empty_text(self.workflow_run_id, "workflow_run_id")
        if self.source_document_ref is not None:
            _require_non_empty_text(self.source_document_ref, "source_document_ref")
        if not isinstance(self.llm_dispatch_preparation, Mapping):
            raise TypeError("llm_dispatch_preparation must be mapping")
        _require_positive_int(self.max_items, "max_items")
        _require_non_empty_text(self.worker_ref, "worker_ref")
        if self.context_payload is not None and not isinstance(
            self.context_payload,
            Mapping,
        ):
            raise TypeError("context_payload must be mapping")


def build_claim_builder_capacity_drain_trigger_command(
    command: BuildClaimBuilderCapacityDrainTriggerCommand,
) -> WorkflowCommand:
    window = _first_capacity_window(command.llm_dispatch_preparation)
    source_scope = command.source_document_ref or "-"
    idempotency_key = (
        "trigger-claim-builder-capacity-drain:"
        f"{command.workflow_run_id}:"
        f"{source_scope}:"
        f"{window['provider']}:"
        f"{window['model_ref']}:"
        f"{window['account_ref']}"
    )
    payload: dict[str, object] = {
        "workflow_run_id": command.workflow_run_id,
        "provider": window["provider"],
        "model_ref": window["model_ref"],
        "account_ref": window["account_ref"],
        "worker_ref": command.worker_ref,
        "max_items": command.max_items,
        "llm_dispatch_preparation": dict(command.llm_dispatch_preparation),
    }
    if command.source_document_ref is not None:
        payload["source_document_ref"] = command.source_document_ref
    if command.context_payload is not None:
        payload.update(command.context_payload)

    return WorkflowCommand(
        command_id=WorkflowCommandId(f"workflow-command:{idempotency_key}"),
        command_type=(
            KnowledgeExtractionCanonicalCommandType.TRIGGER_CLAIM_BUILDER_CAPACITY_DRAIN.value
        ),
        workflow_run_id=command.workflow_run_id,
        idempotency_key=WorkflowIdempotencyKey(idempotency_key),
        payload=payload,
        status=WorkflowCommandStatus.PENDING,
        run_after=command.run_after,
        created_at=command.occurred_at,
        updated_at=command.occurred_at,
    )


def _first_capacity_window(
    llm_dispatch_preparation: Mapping[str, object],
) -> dict[str, str]:
    raw_windows = llm_dispatch_preparation.get("account_capacities")
    if not isinstance(raw_windows, Sequence) or isinstance(raw_windows, str | bytes):
        raise ValueError("llm_dispatch_preparation account_capacities must be sequence")
    active_model_ref = llm_dispatch_preparation.get("active_model_ref")
    windows = tuple(
        window
        for window in raw_windows
        if isinstance(window, Mapping)
        and (
            not isinstance(active_model_ref, str)
            or window.get("model_ref") == active_model_ref
        )
    )
    if not windows:
        raise ValueError("llm_dispatch_preparation must include account capacity")
    selected = windows[0]
    return {
        "provider": _mapping_text(selected, "provider"),
        "model_ref": _mapping_text(selected, "model_ref"),
        "account_ref": _mapping_text(selected, "account_ref"),
    }


def _mapping_text(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"capacity account must include {key}")
    return value


def _require_non_empty_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _require_positive_int(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be positive int")
