from __future__ import annotations

from dataclasses import dataclass, fields
from enum import StrEnum

from .shared import DomainInvariantError


class ParallelFinalizationDecision(StrEnum):
    CAN_FINALIZE = "can_finalize"
    KEEP_DRAINING = "keep_draining"
    BLOCKED_BY_LEASES = "blocked_by_leases"
    WAITING_FOR_FRESH_REGISTRY = "waiting_for_fresh_registry"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ParallelDrainWorkCounts:
    section_ready: int = 0
    section_leased: int = 0
    section_claim_observations_persisted: int = 0
    section_registry_application_queued: int = 0
    section_waiting_for_fresh_registry: int = 0
    section_failed: int = 0
    section_registry_application_applied: int = 0
    section_skipped: int = 0
    registry_ready: int = 0
    registry_leased: int = 0
    registry_waiting_for_fresh_registry: int = 0
    registry_failed: int = 0
    registry_applied: int = 0
    registry_superseded: int = 0

    def __post_init__(self) -> None:
        for field in fields(self):
            value = getattr(self, field.name)
            if value < 0:
                raise DomainInvariantError(
                    f"parallel drain count {field.name} must be non-negative"
                )

    @property
    def active_section_work_count(self) -> int:
        return (
            self.section_ready
            + self.section_leased
            + self.section_claim_observations_persisted
            + self.section_registry_application_queued
        )

    @property
    def active_registry_work_count(self) -> int:
        return self.registry_ready + self.registry_leased

    @property
    def leased_work_count(self) -> int:
        return self.section_leased + self.registry_leased

    @property
    def waiting_for_fresh_registry_count(self) -> int:
        return (
            self.section_waiting_for_fresh_registry
            + self.registry_waiting_for_fresh_registry
        )

    @property
    def failed_work_count(self) -> int:
        return self.section_failed + self.registry_failed

    @property
    def unfinished_work_count(self) -> int:
        return (
            self.active_section_work_count
            + self.active_registry_work_count
            + self.waiting_for_fresh_registry_count
            + self.failed_work_count
        )

    @property
    def terminal_work_count(self) -> int:
        return (
            self.section_registry_application_applied
            + self.section_skipped
            + self.registry_applied
            + self.registry_superseded
        )


@dataclass(frozen=True, slots=True)
class ParallelProcessingIntegrityCounts:
    document_sections_total: int
    section_queue_items_total: int
    claim_observation_artifacts_total: int
    canonicalization_artifacts_total: int


@dataclass(frozen=True, slots=True)
class ParallelFinalizationReadiness:
    decision: ParallelFinalizationDecision
    counts: ParallelDrainWorkCounts
    reason: str

    @property
    def may_finalize(self) -> bool:
        return self.decision is ParallelFinalizationDecision.CAN_FINALIZE


def decide_parallel_finalization(
    counts: ParallelDrainWorkCounts,
) -> ParallelFinalizationReadiness:
    if counts.failed_work_count:
        return ParallelFinalizationReadiness(
            decision=ParallelFinalizationDecision.FAILED,
            counts=counts,
            reason="parallel processing has failed work items",
        )

    if counts.leased_work_count:
        return ParallelFinalizationReadiness(
            decision=ParallelFinalizationDecision.BLOCKED_BY_LEASES,
            counts=counts,
            reason="parallel processing still has leased work items",
        )

    if counts.waiting_for_fresh_registry_count:
        return ParallelFinalizationReadiness(
            decision=ParallelFinalizationDecision.WAITING_FOR_FRESH_REGISTRY,
            counts=counts,
            reason="parallel processing has work items waiting for a fresh registry",
        )

    if counts.active_section_work_count or counts.active_registry_work_count:
        return ParallelFinalizationReadiness(
            decision=ParallelFinalizationDecision.KEEP_DRAINING,
            counts=counts,
            reason="parallel processing still has drainable work items",
        )

    return ParallelFinalizationReadiness(
        decision=ParallelFinalizationDecision.CAN_FINALIZE,
        counts=counts,
        reason="section and registry application queues are drained",
    )


def ensure_parallel_processing_can_finalize(
    counts: ParallelDrainWorkCounts,
) -> None:
    readiness = decide_parallel_finalization(counts)
    if readiness.may_finalize:
        return
    raise DomainInvariantError(
        "parallel processing cannot finalize before queues are drained: "
        f"{readiness.decision.value}"
    )


__all__ = [
    "ParallelDrainWorkCounts",
    "ParallelProcessingIntegrityCounts",
    "ParallelFinalizationDecision",
    "ParallelFinalizationReadiness",
    "decide_parallel_finalization",
    "ensure_parallel_processing_can_finalize",
]
