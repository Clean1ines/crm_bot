from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from src.contexts.knowledge_workbench.application.sagas.claim_builder_dispatch_preparation import (
    ClaimBuilderDispatchPreparationBuilder,
)
from src.contexts.knowledge_workbench.application.sagas.handle_prepare_draft_claim_compaction_dispatch_batch_command import (
    DRAFT_CLAIM_COMPACTION_ACTIVE_MODEL_REF,
    DRAFT_CLAIM_COMPACTION_WORKER_REF,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalCommandType,
)
from src.contexts.workflow_runtime.domain.entities.workflow_command import (
    WorkflowCommand,
)


DRAFT_CLAIM_COMPACTION_DISPATCH_PROFILE_ID = "draft_claim_compaction"
DRAFT_CLAIM_COMPACTION_ESTIMATED_PROMPT_TOKENS = 90_000
DRAFT_CLAIM_COMPACTION_ESTIMATED_COMPLETION_TOKENS = 4_000
DRAFT_CLAIM_COMPACTION_PROVIDER = "groq"
DRAFT_CLAIM_COMPACTION_ACCOUNT_REF = "groq_org_primary"
DRAFT_CLAIM_COMPACTION_LEASE_TTL_SECONDS = 300


@dataclass(frozen=True, slots=True)
class KnowledgeExtractionCommandPayloadRepairPolicy:
    claim_builder_dispatch_preparation_builder: ClaimBuilderDispatchPreparationBuilder

    @classmethod
    def with_defaults(cls) -> "KnowledgeExtractionCommandPayloadRepairPolicy":
        return cls(
            claim_builder_dispatch_preparation_builder=(
                ClaimBuilderDispatchPreparationBuilder()
            ),
        )

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
            return _copy_command_with_payload_value(
                workflow_command=workflow_command,
                key="llm_dispatch_preparation",
                value=self.claim_builder_dispatch_preparation_builder.build_payload(
                    workflow_run_id=workflow_command.workflow_run_id,
                    scheduled_work_item_count=_payload_positive_int(
                        workflow_command.payload,
                        "scheduled_work_item_count",
                    ),
                ),
            )

        if (
            command_type
            is KnowledgeExtractionCanonicalCommandType.PREPARE_DRAFT_CLAIM_COMPACTION_DISPATCH_BATCH
        ):
            scheduled_work_item_count = _payload_positive_int(
                workflow_command.payload,
                "scheduled_work_item_count",
            )
            return _copy_command_with_payload_value(
                workflow_command=workflow_command,
                key="llm_dispatch_preparation",
                value=_draft_claim_compaction_dispatch_preparation_payload(
                    workflow_run_id=workflow_command.workflow_run_id,
                    scheduled_work_item_count=scheduled_work_item_count,
                ),
            )

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


def _draft_claim_compaction_dispatch_preparation_payload(
    *,
    workflow_run_id: str,
    scheduled_work_item_count: int,
) -> dict[str, object]:
    _require_non_empty_text(workflow_run_id, "workflow_run_id")
    _require_positive_int(scheduled_work_item_count, "scheduled_work_item_count")

    estimated_total_tokens = (
        DRAFT_CLAIM_COMPACTION_ESTIMATED_PROMPT_TOKENS
        + DRAFT_CLAIM_COMPACTION_ESTIMATED_COMPLETION_TOKENS
    )
    return {
        "profile": {
            "profile_id": DRAFT_CLAIM_COMPACTION_DISPATCH_PROFILE_ID,
            "estimated_prompt_tokens": (DRAFT_CLAIM_COMPACTION_ESTIMATED_PROMPT_TOKENS),
            "estimated_completion_tokens": (
                DRAFT_CLAIM_COMPACTION_ESTIMATED_COMPLETION_TOKENS
            ),
            "estimated_requests": 1,
        },
        "account_capacities": [
            {
                "provider": DRAFT_CLAIM_COMPACTION_PROVIDER,
                "account_ref": DRAFT_CLAIM_COMPACTION_ACCOUNT_REF,
                "model_ref": DRAFT_CLAIM_COMPACTION_ACTIVE_MODEL_REF,
                "remaining_minute_requests": scheduled_work_item_count,
                "remaining_minute_tokens": (
                    estimated_total_tokens * scheduled_work_item_count
                ),
                "remaining_daily_requests": scheduled_work_item_count,
                "remaining_daily_tokens": (
                    estimated_total_tokens * scheduled_work_item_count
                ),
            }
        ],
        "active_model_ref": DRAFT_CLAIM_COMPACTION_ACTIVE_MODEL_REF,
        "requested_items": scheduled_work_item_count,
        "worker_ref": DRAFT_CLAIM_COMPACTION_WORKER_REF,
        "lease_token_prefix": f"draft-claim-compaction-dispatch:{workflow_run_id}",
        "lease_ttl_seconds": DRAFT_CLAIM_COMPACTION_LEASE_TTL_SECONDS,
    }


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
