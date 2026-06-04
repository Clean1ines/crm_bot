from src.domain.project_plane.knowledge_workbench import (
    ParallelDrainWorkCounts,
    ParallelFinalizationDecision,
    ParallelProcessingIntegrityCounts,
    decide_parallel_canonicalization_readiness,
)


def test_claim_observations_persisted_for_all_sections_can_start_barrier() -> None:
    counts = ParallelDrainWorkCounts(
        section_claim_observations_persisted=3,
    )
    integrity = ParallelProcessingIntegrityCounts(
        document_sections_total=3,
        section_queue_items_total=3,
        claim_observation_artifacts_total=3,
        canonicalization_artifacts_total=0,
    )

    readiness = decide_parallel_canonicalization_readiness(
        counts=counts,
        integrity=integrity,
    )

    assert readiness.decision is ParallelFinalizationDecision.CAN_FINALIZE


def test_claim_observation_status_without_artifacts_keeps_draining() -> None:
    counts = ParallelDrainWorkCounts(
        section_claim_observations_persisted=3,
    )
    integrity = ParallelProcessingIntegrityCounts(
        document_sections_total=3,
        section_queue_items_total=3,
        claim_observation_artifacts_total=2,
        canonicalization_artifacts_total=0,
    )

    readiness = decide_parallel_canonicalization_readiness(
        counts=counts,
        integrity=integrity,
    )

    assert readiness.decision is ParallelFinalizationDecision.KEEP_DRAINING
    assert (
        readiness.reason == "Prompt A section statuses are ahead of persisted artifacts"
    )


def test_partial_section_extraction_keeps_draining() -> None:
    counts = ParallelDrainWorkCounts(
        section_claim_observations_persisted=2,
    )
    integrity = ParallelProcessingIntegrityCounts(
        document_sections_total=3,
        section_queue_items_total=3,
        claim_observation_artifacts_total=2,
        canonicalization_artifacts_total=0,
    )

    readiness = decide_parallel_canonicalization_readiness(
        counts=counts,
        integrity=integrity,
    )

    assert readiness.decision is ParallelFinalizationDecision.KEEP_DRAINING
    assert readiness.reason == "not every section has completed Prompt A extraction"


def test_missing_section_queue_coverage_keeps_draining() -> None:
    counts = ParallelDrainWorkCounts(
        section_claim_observations_persisted=2,
    )
    integrity = ParallelProcessingIntegrityCounts(
        document_sections_total=3,
        section_queue_items_total=2,
        claim_observation_artifacts_total=2,
        canonicalization_artifacts_total=0,
    )

    readiness = decide_parallel_canonicalization_readiness(
        counts=counts,
        integrity=integrity,
    )

    assert readiness.decision is ParallelFinalizationDecision.KEEP_DRAINING
    assert (
        readiness.reason
        == "parallel section queue does not cover every document section"
    )


def test_failed_section_blocks_barrier() -> None:
    counts = ParallelDrainWorkCounts(
        section_claim_observations_persisted=2,
        section_failed=1,
    )
    integrity = ParallelProcessingIntegrityCounts(
        document_sections_total=3,
        section_queue_items_total=3,
        claim_observation_artifacts_total=2,
        canonicalization_artifacts_total=0,
    )

    readiness = decide_parallel_canonicalization_readiness(
        counts=counts,
        integrity=integrity,
    )

    assert readiness.decision is ParallelFinalizationDecision.FAILED


def test_ready_section_keeps_draining_before_barrier() -> None:
    counts = ParallelDrainWorkCounts(
        section_ready=1,
        section_claim_observations_persisted=2,
    )
    integrity = ParallelProcessingIntegrityCounts(
        document_sections_total=3,
        section_queue_items_total=3,
        claim_observation_artifacts_total=2,
        canonicalization_artifacts_total=0,
    )

    readiness = decide_parallel_canonicalization_readiness(
        counts=counts,
        integrity=integrity,
    )

    assert readiness.decision is ParallelFinalizationDecision.KEEP_DRAINING
    assert (
        readiness.reason == "parallel section extraction still has drainable work items"
    )
