from __future__ import annotations

from src.contexts.knowledge_workbench.extraction.application.ports.validated_draft_claim_observation_persistence_port import (
    ValidatedDraftClaimObservationCandidate,
)
from src.contexts.knowledge_workbench.extraction.domain.value_objects.draft_claim_granularity import (
    DraftClaimGranularity,
)


def test_validated_draft_claim_observation_candidate_allows_empty_exclusion_scope() -> (
    None
):
    candidate = ValidatedDraftClaimObservationCandidate(
        workflow_run_id="workflow-1",
        stage_run_id="stage-1",
        prompt_id="faq_claim_observations",
        prompt_version="v1",
        source_document_ref="source-document:1",
        source_unit_ref="source-unit:1",
        source_unit_ordinal=0,
        work_item_id="work-item-1",
        dispatch_attempt_id="attempt-1",
        claim_index=0,
        provider="groq",
        model_ref="qwen/qwen3-32b",
        claim="Product System turns documents into knowledge.",
        granularity=DraftClaimGranularity.ATOMIC,
        possible_questions=("Что делает Product System?",),
        exclusion_scope="",
        evidence_block="Product System turns documents into knowledge.",
        validation_decision="VALID_CLAIMS",
    )

    assert candidate.exclusion_scope == ""
