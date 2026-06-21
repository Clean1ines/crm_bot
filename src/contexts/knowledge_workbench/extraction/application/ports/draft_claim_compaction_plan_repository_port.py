from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_models import (
    DraftClaimCompactionBatchCandidate,
    DraftClaimCompactionBatchForDispatch,
    DraftClaimCompactionBatchReadModel,
    DraftClaimCompactionEdgeCandidate,
    DraftClaimCompactionGroupCandidate,
    DraftClaimCompactionGroupMemberReadModel,
    DraftClaimCompactionGroupReadModel,
    DraftClaimForCompaction,
)


@dataclass(frozen=True, slots=True)
class DraftClaimCompactionPlanPersistenceResult:
    requested_edge_count: int
    inserted_edge_count: int
    requested_group_count: int
    inserted_group_count: int
    requested_member_count: int
    inserted_member_count: int
    requested_batch_count: int
    inserted_batch_count: int
    already_exists_count: int


class DraftClaimCompactionPlanRepositoryPort(Protocol):
    async def get_compaction_batch_by_ref(
        self,
        *,
        batch_ref: str,
    ) -> DraftClaimCompactionBatchForDispatch | None: ...

    async def list_claims_for_compaction_batch(
        self,
        *,
        batch_ref: str,
    ) -> tuple[DraftClaimForCompaction, ...]: ...

    async def list_claims_for_compaction(
        self,
        *,
        workflow_run_id: str,
        embedding_model_id: str,
    ) -> tuple[DraftClaimForCompaction, ...]: ...

    async def list_cluster_groups_for_workflow(
        self,
        *,
        workflow_run_id: str,
        limit: int,
        offset: int,
    ) -> tuple[DraftClaimCompactionGroupReadModel, ...]: ...

    async def list_cluster_batches_for_workflow(
        self,
        *,
        workflow_run_id: str,
    ) -> tuple[DraftClaimCompactionBatchReadModel, ...]: ...

    async def list_cluster_members_for_group(
        self,
        *,
        workflow_run_id: str,
        group_ref: str,
        limit: int,
        offset: int,
    ) -> tuple[DraftClaimCompactionGroupMemberReadModel, ...]: ...

    async def persist_compaction_plan(
        self,
        *,
        edges: tuple[DraftClaimCompactionEdgeCandidate, ...],
        groups: tuple[DraftClaimCompactionGroupCandidate, ...],
        batches: tuple[DraftClaimCompactionBatchCandidate, ...],
        created_at: datetime,
    ) -> DraftClaimCompactionPlanPersistenceResult: ...
