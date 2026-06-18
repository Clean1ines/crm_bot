from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_progress import (
    DraftClaimCompactionProgressSummary,
)
from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_prompt_contract import (
    DraftClaimReducedRewriteOutput,
)
from src.contexts.knowledge_workbench.extraction.application.models.enriched_draft_claim_compaction_output import (
    EnrichedDraftClaimCompactionOutputClaim,
)
from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_reduction_models import (
    DraftClaimCompactionNode,
    DraftClaimCompactionPlannerState,
)


@dataclass(frozen=True, slots=True)
class DraftClaimCompactionReductionStatePersistenceResult:
    requested_node_count: int
    inserted_node_count: int
    requested_source_count: int
    inserted_source_count: int
    requested_comparison_count: int
    inserted_comparison_count: int
    already_exists_count: int

    def __post_init__(self) -> None:
        for field_name, value in (
            ("requested_node_count", self.requested_node_count),
            ("inserted_node_count", self.inserted_node_count),
            ("requested_source_count", self.requested_source_count),
            ("inserted_source_count", self.inserted_source_count),
            ("requested_comparison_count", self.requested_comparison_count),
            ("inserted_comparison_count", self.inserted_comparison_count),
            ("already_exists_count", self.already_exists_count),
        ):
            if not isinstance(value, int):
                raise TypeError(f"{field_name} must be int")
            if value < 0:
                raise ValueError(f"{field_name} must be >= 0")


@dataclass(frozen=True, slots=True)
class DraftClaimCompactionApplyPersistenceResult:
    inserted_node_count: int
    updated_node_count: int
    inserted_source_count: int
    inserted_comparison_count: int
    superseded_node_count: int
    already_exists_count: int

    def __post_init__(self) -> None:
        for field_name, value in (
            ("inserted_node_count", self.inserted_node_count),
            ("updated_node_count", self.updated_node_count),
            ("inserted_source_count", self.inserted_source_count),
            ("inserted_comparison_count", self.inserted_comparison_count),
            ("superseded_node_count", self.superseded_node_count),
            ("already_exists_count", self.already_exists_count),
        ):
            if not isinstance(value, int):
                raise TypeError(f"{field_name} must be int")
            if value < 0:
                raise ValueError(f"{field_name} must be >= 0")


class DraftClaimCompactionReductionStateRepositoryPort(Protocol):
    async def summarize_compaction_progress(
        self,
        *,
        workflow_run_id: str,
    ) -> DraftClaimCompactionProgressSummary: ...

    async def load_planner_state(
        self,
        *,
        workflow_run_id: str,
        group_ref: str,
    ) -> DraftClaimCompactionPlannerState | None: ...

    async def seed_initial_planner_state(
        self,
        *,
        workflow_run_id: str,
        group_ref: str,
        raw_nodes: tuple[DraftClaimCompactionNode, ...],
        created_at: datetime,
    ) -> DraftClaimCompactionReductionStatePersistenceResult: ...

    async def apply_compacted_claims_result(
        self,
        *,
        workflow_run_id: str,
        group_ref: str,
        batch_ref: str,
        work_item_id: str,
        round_index: int,
        compacted_claims: tuple[EnrichedDraftClaimCompactionOutputClaim, ...],
        compared_node_refs: tuple[str, ...] = (),
        created_at: datetime,
    ) -> DraftClaimCompactionApplyPersistenceResult: ...

    async def apply_reduced_rewrite_result(
        self,
        *,
        workflow_run_id: str,
        group_ref: str,
        batch_ref: str,
        work_item_id: str,
        round_index: int,
        source_node_refs: tuple[str, ...],
        rewrite: DraftClaimReducedRewriteOutput,
        created_at: datetime,
    ) -> DraftClaimCompactionApplyPersistenceResult: ...

    async def list_final_compacted_nodes_for_preview(
        self,
        *,
        workflow_run_id: str,
    ) -> tuple[DraftClaimCompactionNode, ...]: ...

    async def count_active_raw_nodes(
        self,
        *,
        workflow_run_id: str,
    ) -> int: ...
