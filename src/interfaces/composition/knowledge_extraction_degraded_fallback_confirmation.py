from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, cast

import asyncpg

from src.contexts.knowledge_workbench.application.sagas.confirm_draft_claim_compaction_degraded_fallback import (
    ConfirmDraftClaimCompactionDegradedFallback,
    ConfirmDraftClaimCompactionDegradedFallbackCommand,
    ConfirmDraftClaimCompactionDegradedFallbackResult,
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
