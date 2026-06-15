from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_prompt_contract import (
    DraftClaimCompactionOutputClaim,
)
from src.contexts.knowledge_workbench.extraction.application.policies.draft_claim_compaction_output_enricher import (
    DraftClaimCompactionOutputEnricher,
)
from src.contexts.knowledge_workbench.extraction.application.ports.draft_claim_observation_read_repository_port import (
    DraftClaimObservationReadModel,
)


def _raw_claim(
    *,
    observation_ref: str,
    possible_questions: tuple[str, ...],
    exclusion_scope: str,
    evidence_block: str,
) -> DraftClaimObservationReadModel:
    return DraftClaimObservationReadModel(
        observation_ref=observation_ref,
        source_unit_ref="source-unit-1",
        claim=f"Raw claim {observation_ref}",
        granularity="atomic",
        possible_questions=possible_questions,
        exclusion_scope=exclusion_scope,
        evidence_block=evidence_block,
        workflow_run_id=None,
        stage_run_id=None,
        work_item_id=None,
        work_item_attempt_id=None,
        llm_task_id=None,
        llm_attempt_id=None,
        prompt_id=None,
        prompt_version=None,
        claim_index=None,
        created_at=datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc),
    )


def test_enriches_compacted_claim_from_source_raw_claims_exactly() -> None:
    enriched = DraftClaimCompactionOutputEnricher().enrich(
        output_claims=(
            DraftClaimCompactionOutputClaim(
                key="merged",
                claim="Merged claim.",
                claim_kind="definition",
                granularity="atomic",
                source_claim_refs=("claim-1", "claim-2"),
                triples=(),
                merge_decision="merged",
            ),
        ),
        source_claims=(
            _raw_claim(
                observation_ref="claim-1",
                possible_questions=("Q1", "Q2"),
                exclusion_scope="not X",
                evidence_block="E1",
            ),
            _raw_claim(
                observation_ref="claim-2",
                possible_questions=("Q2", "Q3"),
                exclusion_scope="not X",
                evidence_block="E2",
            ),
        ),
    )

    claim = enriched.compacted_claims[0]
    assert claim.possible_questions == ("Q1", "Q2", "Q3")
    assert claim.exclusion_scope == "not X"
    assert claim.evidence_block == "E1\n\nE2"
    assert claim.to_json_dict()["possible_questions"] == ["Q1", "Q2", "Q3"]


def test_raises_when_source_claim_ref_is_missing() -> None:
    with pytest.raises(
        ValueError, match="source claim for compaction output is missing"
    ):
        DraftClaimCompactionOutputEnricher().enrich(
            output_claims=(
                DraftClaimCompactionOutputClaim(
                    key="merged",
                    claim="Merged claim.",
                    claim_kind="definition",
                    granularity="atomic",
                    source_claim_refs=("claim-999",),
                    triples=(),
                    merge_decision="unmerged",
                ),
            ),
            source_claims=(),
        )
