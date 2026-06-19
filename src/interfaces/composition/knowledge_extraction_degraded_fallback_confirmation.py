from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, cast

import asyncpg

from src.contexts.knowledge_workbench.application.sagas.confirm_draft_claim_compaction_degraded_fallback import (
    ConfirmDraftClaimCompactionDegradedFallback,
    ConfirmDraftClaimCompactionDegradedFallbackCommand,
    ConfirmDraftClaimCompactionDegradedFallbackResult,
    DraftClaimCompactionDegradedFallbackDecision,
)
from src.contexts.knowledge_workbench.application.sagas.handle_apply_draft_claim_compaction_result_command import (
    _provider_messages_for_next_work_item,
)
from src.contexts.execution_runtime.application.use_cases.ensure_work_items_scheduled import (
    EnsureWorkItemsScheduled,
    EnsureWorkItemsScheduledCommand,
    WorkItemSchedulePlan,
)
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.execution_runtime.infrastructure.postgres.postgres_work_item_scheduling_repository import (
    PostgresWorkItemSchedulingRepository,
)
from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_reduction_models import (
    DraftClaimCompactionNextWorkItem,
    DraftClaimCompactionNextWorkItemType,
)
from src.contexts.knowledge_workbench.extraction.infrastructure.postgres.postgres_draft_claim_compaction_reduction_state_repository import (
    PostgresDraftClaimCompactionReductionStateRepository,
)
from src.contexts.knowledge_workbench.extraction.infrastructure.postgres.postgres_draft_claim_observation_read_repository import (
    PostgresDraftClaimObservationReadRepository,
)
from src.contexts.knowledge_workbench.infrastructure.postgres.postgres_draft_claim_compaction_degraded_fallback_decision_repository import (
    PostgresDraftClaimCompactionDegradedFallbackDecisionRepository,
)
from src.contexts.workflow_runtime.infrastructure.postgres.postgres_workflow_runtime_unit_of_work import (
    PostgresWorkflowRuntimeUnitOfWork,
)


class AsyncDegradedFallbackConfirmationPool(Protocol):
    async def acquire(self) -> object: ...

    async def release(self, connection: object) -> None: ...


@dataclass(frozen=True, slots=True)
class RunKnowledgeExtractionDegradedFallbackConfirmation:
    pool: AsyncDegradedFallbackConfirmationPool

    async def execute(
        self,
        command: ConfirmDraftClaimCompactionDegradedFallbackCommand,
    ) -> ConfirmDraftClaimCompactionDegradedFallbackResult:
        connection = await self.pool.acquire()
        typed_connection = cast(asyncpg.Connection, connection)
        workflow_unit_of_work = PostgresWorkflowRuntimeUnitOfWork(typed_connection)
        await workflow_unit_of_work.start()
        try:
            result = await ConfirmDraftClaimCompactionDegradedFallback(
                decision_repository=(
                    PostgresDraftClaimCompactionDegradedFallbackDecisionRepository(
                        typed_connection
                    )
                ),
                workflow_unit_of_work=workflow_unit_of_work,
                degraded_fallback_scheduler=_PostgresDegradedFallbackScheduler(
                    typed_connection
                ),
            ).execute(command)
            await workflow_unit_of_work.commit()
            return result
        except Exception:
            await workflow_unit_of_work.rollback()
            raise
        finally:
            await self.pool.release(connection)


def make_knowledge_extraction_degraded_fallback_confirmation(
    *,
    pool: AsyncDegradedFallbackConfirmationPool,
) -> RunKnowledgeExtractionDegradedFallbackConfirmation:
    return RunKnowledgeExtractionDegradedFallbackConfirmation(pool=pool)


@dataclass(frozen=True, slots=True)
class _PostgresDegradedFallbackScheduler:
    connection: asyncpg.Connection

    async def schedule_degraded_work(
        self,
        *,
        workflow_run_id: str,
        decision: DraftClaimCompactionDegradedFallbackDecision,
        created_at: datetime,
    ) -> None:
        if decision.group_ref is None or decision.resume_work_type is None:
            raise ValueError("graph fallback decision is incomplete")
        if decision.estimated_prompt_tokens is None:
            raise ValueError("estimated_prompt_tokens is required")
        if decision.estimated_completion_tokens is None:
            raise ValueError("estimated_completion_tokens is required")

        resume_work_type = DraftClaimCompactionNextWorkItemType(
            decision.resume_work_type
        )
        next_work_item = DraftClaimCompactionNextWorkItem(
            work_type=resume_work_type,
            node_refs=decision.node_refs,
            primary_model_id=decision.degraded_model_ref,
            estimated_prompt_tokens=decision.estimated_prompt_tokens,
            estimated_completion_tokens=decision.estimated_completion_tokens,
        )
        state_repository = PostgresDraftClaimCompactionReductionStateRepository(
            self.connection
        )
        observation_repository = PostgresDraftClaimObservationReadRepository(
            self.connection
        )
        provider_messages = await _provider_messages_for_next_work_item(
            workflow_run_id=workflow_run_id,
            group_ref=decision.group_ref,
            next_work_item=next_work_item,
            compaction_reduction_state_repository=state_repository,
            draft_claim_observation_read_repository=observation_repository,
        )
        batch_ref = _graph_fallback_batch_ref(
            group_ref=decision.group_ref,
            node_refs=decision.node_refs,
            model_ref=decision.degraded_model_ref,
        )
        work_item_id = f"claim-compaction:{workflow_run_id}:{batch_ref}"
        result = await EnsureWorkItemsScheduled(
            PostgresWorkItemSchedulingRepository(self.connection)
        ).execute(
            EnsureWorkItemsScheduledCommand(
                plans=(
                    WorkItemSchedulePlan(
                        work_item_id=work_item_id,
                        work_kind=WorkKind(
                            "knowledge_workbench.draft_claim_compaction"
                        ),
                        idempotency_key=work_item_id,
                        payload={
                            "workflow_run_id": workflow_run_id,
                            "group_ref": decision.group_ref,
                            "batch_ref": batch_ref,
                            "prompt_variant": resume_work_type.value,
                            "model_id": decision.degraded_model_ref,
                            "node_refs": list(decision.node_refs),
                            "provider_messages": list(provider_messages),
                            "llm_capacity_estimate": {
                                "estimated_input_tokens": (
                                    decision.estimated_prompt_tokens
                                ),
                                "reserved_output_tokens": (
                                    decision.estimated_completion_tokens
                                ),
                                "estimated_total_tokens": (
                                    decision.estimated_prompt_tokens
                                    + decision.estimated_completion_tokens
                                ),
                            },
                        },
                    ),
                )
            )
        )
        if result.conflict_count:
            raise ValueError("degraded compaction work item schedule conflict")


def _graph_fallback_batch_ref(
    *,
    group_ref: str,
    node_refs: tuple[str, ...],
    model_ref: str,
) -> str:
    digest = hashlib.sha256(
        "|".join((group_ref, *node_refs, model_ref)).encode("utf-8")
    ).hexdigest()[:24]
    return f"user-degraded:{group_ref}:{digest}"
