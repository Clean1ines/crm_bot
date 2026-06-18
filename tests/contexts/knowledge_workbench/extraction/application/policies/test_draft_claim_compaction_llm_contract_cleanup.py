from __future__ import annotations

import pytest

from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_models import (
    DraftClaimForCompaction,
)
from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_prompt_contract import (
    DraftClaimCompactionClaimKind,
    DraftClaimCompactionMergeDecision,
    DraftClaimCompactionOutputClaim,
    DraftClaimCompactionPromptClaim,
    DraftClaimCompactionTriple,
)
from src.contexts.knowledge_workbench.extraction.application.policies.draft_claim_compaction_output_validator import (
    DraftClaimCompactionOutputValidator,
    InvalidDraftClaimCompactionOutput,
)
from src.contexts.knowledge_workbench.extraction.application.policies.draft_claim_compaction_prompt_payload_builder import (
    DraftClaimCompactionPromptPayloadBuilder,
)


def test_prompt_claim_payload_excludes_exclusion_scope_and_granularity() -> None:
    payload = DraftClaimCompactionPromptPayloadBuilder().build_draft_vs_draft_payload(
        (
            DraftClaimForCompaction(
                observation_ref="claim-1",
                embedding_ref="embedding:claim-1",
                workflow_run_id="workflow-1",
                source_document_ref="document-1",
                source_unit_ref="unit:claim-1",
                claim="Axole turns documents into checked support knowledge.",
                possible_questions=("What is Axole?",),
                exclusion_scope=("pricing",),
                granularity="atomic",
                embedding_text="Axole turns documents into checked support knowledge.",
                embedding_model_id="openai/gpt-oss-120b",
                dimensions=2,
                vector=(1.0, 0.0),
            ),
        )
    )

    assert payload.to_json_dict() == {
        "claims": [
            {
                "id": "claim-1",
                "claim": "Axole turns documents into checked support knowledge.",
                "questions": ["What is Axole?"],
            }
        ]
    }


def test_prompt_claim_constructor_has_no_exclusion_scope_or_granularity() -> None:
    claim = DraftClaimCompactionPromptClaim(
        claim_id="claim-1",
        claim="A claim.",
        questions=("Q?",),
    )

    assert claim.to_json_dict() == {
        "id": "claim-1",
        "claim": "A claim.",
        "questions": ["Q?"],
    }


def test_output_validator_accepts_compaction_without_granularity() -> None:
    output = DraftClaimCompactionOutputValidator().validate(
        payload={
            "compacted_claims": [
                {
                    "key": "axole_definition",
                    "claim": "Axole turns documents into checked support knowledge.",
                    "claim_kind": "definition",
                    "source_claim_refs": ["claim-1"],
                    "triples": [],
                    "merge_decision": "unmerged",
                }
            ]
        },
        input_claim_refs=("claim-1",),
    )

    assert output.compacted_claims[0] == DraftClaimCompactionOutputClaim(
        key="axole_definition",
        claim="Axole turns documents into checked support knowledge.",
        claim_kind=DraftClaimCompactionClaimKind.DEFINITION,
        source_claim_refs=("claim-1",),
        triples=(),
        merge_decision=DraftClaimCompactionMergeDecision.UNMERGED,
    )


def test_output_validator_rejects_granularity_from_llm_output() -> None:
    with pytest.raises(InvalidDraftClaimCompactionOutput):
        DraftClaimCompactionOutputValidator().validate(
            payload={
                "compacted_claims": [
                    {
                        "key": "axole_definition",
                        "claim": "Axole turns documents into checked support knowledge.",
                        "claim_kind": "definition",
                        "granularity": "atomic",
                        "source_claim_refs": ["claim-1"],
                        "triples": [],
                        "merge_decision": "unmerged",
                    }
                ]
            },
            input_claim_refs=("claim-1",),
        )


def test_output_claim_json_excludes_granularity() -> None:
    claim = DraftClaimCompactionOutputClaim(
        key="axole_capability",
        claim="Axole supports Telegram customer support.",
        claim_kind="capability",
        source_claim_refs=("claim-1", "claim-2"),
        triples=(
            DraftClaimCompactionTriple(
                subject="Axole",
                predicate="supports",
                object="Telegram customer support",
                qualifiers=(),
            ),
        ),
        merge_decision="merged",
    )

    assert claim.to_json_dict() == {
        "key": "axole_capability",
        "claim": "Axole supports Telegram customer support.",
        "claim_kind": "capability",
        "source_claim_refs": ["claim-1", "claim-2"],
        "triples": [
            {
                "subject": "Axole",
                "predicate": "supports",
                "object": "Telegram customer support",
                "qualifiers": [],
            }
        ],
        "merge_decision": "merged",
    }
