from __future__ import annotations

from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_models import (
    DraftClaimCompactionGroupCandidate,
    DraftClaimForCompaction,
)
from src.contexts.knowledge_workbench.extraction.application.policies.draft_claim_compaction_batch_budget_policy import (
    DraftClaimCompactionBatchBudgetPolicy,
)


def _claim(ref: str) -> DraftClaimForCompaction:
    return DraftClaimForCompaction(
        observation_ref=ref,
        embedding_ref=f"embedding:{ref}",
        workflow_run_id="workflow-1",
        source_document_ref="document-1",
        source_unit_ref=f"unit:{ref}",
        claim=f"Claim {ref}",
        possible_questions=(f"Question {ref}?",),
        exclusion_scope=(),
        granularity="atomic",
        embedding_text=f"Claim {ref}",
        embedding_model_id="sentence-transformers/all-MiniLM-L6-v2",
        dimensions=2,
        vector=(1.0, 0.0),
    )


def _group(ref: str, members: tuple[str, ...]) -> DraftClaimCompactionGroupCandidate:
    return DraftClaimCompactionGroupCandidate(
        group_ref=ref,
        workflow_run_id="workflow-1",
        source_document_ref="document-1",
        embedding_model_id="sentence-transformers/all-MiniLM-L6-v2",
        group_algorithm="candidate_connected_components_v1",
        group_threshold=0.78,
        member_observation_refs=members,
        member_embedding_refs=tuple(f"embedding:{member}" for member in members),
        member_source_unit_refs=tuple(f"unit:{member}" for member in members),
        estimated_input_tokens=0,
        requires_split=False,
    )


def test_singleton_group_gets_single_draft_claim_enrichment_prompt_variant() -> None:
    claims = (_claim("claim-a"),)
    groups = (_group("group-a", ("claim-a",)),)

    plan = DraftClaimCompactionBatchBudgetPolicy().build_batches(claims, groups)

    assert len(plan.batches) == 1
    assert plan.batches[0].prompt_variant == "single_draft_claim_enrichment"
    assert plan.batches[0].member_observation_refs == ("claim-a",)


def test_multi_member_group_keeps_draft_vs_draft_prompt_variant() -> None:
    claims = (_claim("claim-a"), _claim("claim-b"))
    groups = (_group("group-a", ("claim-a", "claim-b")),)

    plan = DraftClaimCompactionBatchBudgetPolicy().build_batches(claims, groups)

    assert len(plan.batches) == 1
    assert plan.batches[0].prompt_variant == "draft_vs_draft"
    assert plan.batches[0].member_observation_refs == ("claim-a", "claim-b")


def test_capacity_split_inside_multi_member_group_does_not_schedule_singleton_chunks() -> (
    None
):
    claims = (_claim("claim-a"), _claim("claim-b"))
    groups = (_group("group-a", ("claim-a", "claim-b")),)

    plan = DraftClaimCompactionBatchBudgetPolicy(
        max_input_tokens=2052,
        prompt_reserve_tokens=2050,
        input_safety_multiplier=1,
    ).build_batches(claims, groups)

    assert plan.groups[0].member_count == 2
    assert plan.groups[0].requires_split is True
    assert plan.batches == ()


def test_singleton_chunk_inside_larger_group_waits_for_compacted_frontier() -> None:
    claims = tuple(_claim(f"claim-{index}") for index in range(3))
    groups = (_group("group-a", tuple(claim.observation_ref for claim in claims)),)

    plan = DraftClaimCompactionBatchBudgetPolicy(max_input_tokens=2145).build_batches(
        claims,
        groups,
    )

    assert plan.groups[0].member_count == 3
    assert plan.groups[0].requires_split is True
    assert plan.batches == ()
