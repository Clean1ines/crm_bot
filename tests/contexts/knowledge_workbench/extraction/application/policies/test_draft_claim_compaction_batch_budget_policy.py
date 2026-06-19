from __future__ import annotations

from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_models import (
    DraftClaimCompactionGroupCandidate,
    DraftClaimForCompaction,
)
from src.contexts.knowledge_workbench.extraction.application.policies.draft_claim_compaction_batch_budget_policy import (
    DraftClaimCompactionBatchBudgetPolicy,
)


def _claim(ref: str, text: str = "short claim") -> DraftClaimForCompaction:
    return DraftClaimForCompaction(
        observation_ref=ref,
        embedding_ref=f"embedding:{ref}",
        workflow_run_id="workflow-1",
        source_document_ref="document-1",
        source_unit_ref=f"unit:{ref}",
        claim=text,
        possible_questions=("What is it?",),
        exclusion_scope=(),
        granularity="atomic",
        embedding_text=text,
        embedding_model_id="openai/gpt-oss-120b",
        dimensions=2,
        vector=(1.0, 0.0),
    )


def _group(refs: tuple[str, ...]) -> DraftClaimCompactionGroupCandidate:
    return DraftClaimCompactionGroupCandidate(
        group_ref="group-1",
        workflow_run_id="workflow-1",
        source_document_ref="document-1",
        embedding_model_id="openai/gpt-oss-120b",
        group_algorithm="test",
        group_threshold=0.78,
        member_observation_refs=refs,
        member_embedding_refs=tuple(f"embedding:{ref}" for ref in refs),
        member_source_unit_refs=tuple(f"unit:{ref}" for ref in refs),
        estimated_input_tokens=0,
        requires_split=False,
    )


def test_small_group_creates_one_draft_vs_draft_batch() -> None:
    plan = DraftClaimCompactionBatchBudgetPolicy().build_batches(
        (_claim("claim-a"), _claim("claim-b")),
        (_group(("claim-a", "claim-b")),),
    )

    assert len(plan.batches) == 1
    assert plan.batches[0].prompt_variant == "draft_vs_draft"
    assert plan.batches[0].model_id == "openai/gpt-oss-120b"
    assert plan.groups[0].requires_split is False


def test_default_batches_fit_one_gpt_oss_free_plan_capacity_window() -> None:
    claims = (
        _claim("claim-a", "a" * 5600),
        _claim("claim-b", "b" * 5600),
    )

    plan = DraftClaimCompactionBatchBudgetPolicy().build_batches(
        claims,
        (_group(("claim-a", "claim-b")),),
    )

    assert len(plan.batches) == 2
    for batch in plan.batches:
        assert 2050 + batch.estimated_input_tokens * 2 <= 8000


def test_oversized_group_creates_multiple_deterministic_batches() -> None:
    claims = (
        _claim("claim-a", "a" * 1000),
        _claim("claim-b", "b" * 1000),
        _claim("claim-c", "c" * 1000),
    )
    policy = DraftClaimCompactionBatchBudgetPolicy(
        max_input_tokens=700,
        prompt_reserve_tokens=100,
    )

    first = policy.build_batches(claims, (_group(("claim-a", "claim-b", "claim-c")),))
    second = policy.build_batches(claims, (_group(("claim-a", "claim-b", "claim-c")),))

    assert len(first.batches) > 1
    assert first.groups[0].requires_split is True
    assert tuple(batch.batch_ref for batch in first.batches) == tuple(
        batch.batch_ref for batch in second.batches
    )
    assert {batch.model_id for batch in first.batches} == {"openai/gpt-oss-120b"}
