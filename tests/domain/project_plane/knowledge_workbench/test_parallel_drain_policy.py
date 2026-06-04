from __future__ import annotations

import pytest

from src.domain.project_plane.knowledge_workbench.parallel_drain_policy import (
    ParallelDrainWorkCounts,
    ParallelFinalizationDecision,
    decide_parallel_finalization,
    ensure_parallel_processing_can_finalize,
)
from src.domain.project_plane.knowledge_workbench import DomainInvariantError


def test_parallel_processing_can_finalize_only_when_non_terminal_queues_are_empty() -> (
    None
):
    counts = ParallelDrainWorkCounts(
        section_registry_application_applied=6,
        registry_applied=6,
    )

    readiness = decide_parallel_finalization(counts)

    assert readiness.decision is ParallelFinalizationDecision.CAN_FINALIZE
    assert readiness.may_finalize is True
    ensure_parallel_processing_can_finalize(counts)


def test_parallel_processing_keeps_draining_ready_section_or_registry_items() -> None:
    counts = ParallelDrainWorkCounts(section_ready=1, registry_ready=1)

    readiness = decide_parallel_finalization(counts)

    assert readiness.decision is ParallelFinalizationDecision.KEEP_DRAINING
    assert readiness.may_finalize is False

    with pytest.raises(DomainInvariantError, match="keep_draining"):
        ensure_parallel_processing_can_finalize(counts)


def test_parallel_processing_blocks_finalization_while_items_are_leased() -> None:
    counts = ParallelDrainWorkCounts(section_leased=1, registry_leased=1)

    readiness = decide_parallel_finalization(counts)

    assert readiness.decision is ParallelFinalizationDecision.BLOCKED_BY_LEASES
    assert readiness.may_finalize is False


def test_parallel_processing_waits_when_rebase_items_need_fresh_registry() -> None:
    counts = ParallelDrainWorkCounts(
        section_waiting_for_fresh_registry=1,
        registry_waiting_for_fresh_registry=1,
    )

    readiness = decide_parallel_finalization(counts)

    assert readiness.decision is ParallelFinalizationDecision.WAITING_FOR_FRESH_REGISTRY
    assert readiness.may_finalize is False


def test_parallel_processing_failed_items_dominate_finalization_decision() -> None:
    counts = ParallelDrainWorkCounts(
        section_failed=1,
        section_leased=1,
        registry_ready=1,
    )

    readiness = decide_parallel_finalization(counts)

    assert readiness.decision is ParallelFinalizationDecision.FAILED
    assert readiness.may_finalize is False


def test_parallel_drain_counts_reject_negative_values() -> None:
    with pytest.raises(DomainInvariantError, match="non-negative"):
        ParallelDrainWorkCounts(section_ready=-1)


def test_registry_application_queued_section_blocks_finalization() -> None:
    counts = ParallelDrainWorkCounts(section_registry_application_queued=1)

    readiness = decide_parallel_finalization(counts)

    assert counts.active_section_work_count == 1
    assert counts.unfinished_work_count == 1
    assert counts.terminal_work_count == 0
    assert readiness.decision is ParallelFinalizationDecision.KEEP_DRAINING
    assert readiness.may_finalize is False

    with pytest.raises(DomainInvariantError, match="keep_draining"):
        ensure_parallel_processing_can_finalize(counts)


def test_registry_application_applied_section_is_terminal_and_allows_finalization() -> (
    None
):
    counts = ParallelDrainWorkCounts(
        section_registry_application_applied=1,
        registry_applied=1,
    )

    readiness = decide_parallel_finalization(counts)

    assert counts.active_section_work_count == 0
    assert counts.active_registry_work_count == 0
    assert counts.unfinished_work_count == 0
    assert counts.terminal_work_count == 2
    assert readiness.decision is ParallelFinalizationDecision.CAN_FINALIZE
    assert readiness.may_finalize is True

    ensure_parallel_processing_can_finalize(counts)
