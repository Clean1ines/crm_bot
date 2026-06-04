from src.domain.project_plane.knowledge_workbench import (
    ParallelDrainWorkCounts,
    ParallelFinalizationDecision,
    ParallelProcessingIntegrityCounts,
    decide_parallel_canonicalization_readiness,
)


def test_barrier_waits_until_every_prompt_a_artifact_has_local_claim_retrieval_index() -> None:
    counts = ParallelDrainWorkCounts(
        section_claim_observations_persisted=3,
    )
    integrity = ParallelProcessingIntegrityCounts(
        document_sections_total=3,
        section_queue_items_total=3,
        claim_observation_artifacts_total=3,
        canonicalization_artifacts_total=0,
        local_claim_retrieval_indexed_artifacts_total=2,
    )

    readiness = decide_parallel_canonicalization_readiness(
        counts=counts,
        integrity=integrity,
    )

    assert readiness.decision is ParallelFinalizationDecision.KEEP_DRAINING
    assert readiness.reason == (
        "local claim retrieval surface is not indexed for every Prompt A artifact"
    )


def test_barrier_can_start_after_prompt_a_artifacts_are_indexed_for_retrieval() -> None:
    counts = ParallelDrainWorkCounts(
        section_claim_observations_persisted=3,
    )
    integrity = ParallelProcessingIntegrityCounts(
        document_sections_total=3,
        section_queue_items_total=3,
        claim_observation_artifacts_total=3,
        canonicalization_artifacts_total=0,
        local_claim_retrieval_indexed_artifacts_total=3,
    )

    readiness = decide_parallel_canonicalization_readiness(
        counts=counts,
        integrity=integrity,
    )

    assert readiness.decision is ParallelFinalizationDecision.CAN_FINALIZE
    assert readiness.reason == "all section claim observations are indexed for retrieval"
