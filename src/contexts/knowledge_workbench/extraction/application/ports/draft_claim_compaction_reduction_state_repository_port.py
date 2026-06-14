from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

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


class DraftClaimCompactionReductionStateRepositoryPort(Protocol):
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
