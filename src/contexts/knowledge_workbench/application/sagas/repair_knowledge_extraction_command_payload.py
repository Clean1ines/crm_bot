from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalCommandType,
)
from src.contexts.workflow_runtime.domain.entities.workflow_command import (
    WorkflowCommand,
)


@dataclass(frozen=True, slots=True)
class KnowledgeExtractionCommandPayloadRepairPolicy:
    @classmethod
    def with_defaults(cls) -> "KnowledgeExtractionCommandPayloadRepairPolicy":
        return cls()

    def repair(
        self,
        *,
        workflow_command: WorkflowCommand,
        command_type: KnowledgeExtractionCanonicalCommandType,
    ) -> WorkflowCommand:
        if not isinstance(workflow_command, WorkflowCommand):
            raise TypeError("workflow_command must be WorkflowCommand")
        if not isinstance(command_type, KnowledgeExtractionCanonicalCommandType):
            raise TypeError(
                "command_type must be KnowledgeExtractionCanonicalCommandType"
            )

        if _has_dispatch_preparation(workflow_command.payload):
            return workflow_command

        if (
            command_type
            is KnowledgeExtractionCanonicalCommandType.PREPARE_CLAIM_BUILDER_DISPATCH_BATCH
        ):
            return workflow_command

        if (
            command_type
            is KnowledgeExtractionCanonicalCommandType.PREPARE_DRAFT_CLAIM_COMPACTION_DISPATCH_BATCH
        ):
            return workflow_command

        return workflow_command


def repair_knowledge_extraction_command_payload(
    *,
    workflow_command: WorkflowCommand,
    command_type: KnowledgeExtractionCanonicalCommandType,
) -> WorkflowCommand:
    return KnowledgeExtractionCommandPayloadRepairPolicy.with_defaults().repair(
        workflow_command=workflow_command,
        command_type=command_type,
    )


def _has_dispatch_preparation(payload: Mapping[str, object]) -> bool:
    return payload.get("llm_dispatch_preparation") is not None


def _copy_command_with_payload_value(
    *,
    workflow_command: WorkflowCommand,
    key: str,
    value: object,
) -> WorkflowCommand:
    _require_non_empty_text(key, "key")
    payload = dict(workflow_command.payload)
    payload[key] = value
    return WorkflowCommand(
        command_id=workflow_command.command_id,
        command_type=workflow_command.command_type,
        workflow_run_id=workflow_command.workflow_run_id,
        idempotency_key=workflow_command.idempotency_key,
        payload=payload,
        status=workflow_command.status,
        run_after=workflow_command.run_after,
        created_at=workflow_command.created_at,
        updated_at=workflow_command.updated_at,
    )


def _payload_positive_int(payload: Mapping[str, object], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"workflow command payload must include positive int {key}")
    if value <= 0:
        raise ValueError(f"workflow command payload must include positive int {key}")
    return value


def _require_non_empty_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _require_positive_int(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be int")
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")
