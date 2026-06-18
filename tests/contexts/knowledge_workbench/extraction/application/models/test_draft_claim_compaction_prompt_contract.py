from __future__ import annotations

import pytest

from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_prompt_contract import (
    DraftClaimCompactionOutputClaim,
    DraftClaimCompactionPromptClaim,
    DraftClaimCompactionPromptPayload,
    DraftClaimCompactionTriple,
    DraftClaimReducedRewriteInputClaim,
    DraftClaimReducedRewriteOutput,
    DraftClaimReducedRewritePayload,
)


def test_prompt_claim_serializes_minimal_input_shape() -> None:
    claim = DraftClaimCompactionPromptClaim(
        claim_id="claim-1",
        claim="Product supports refunds",
        questions=("Does it support refunds?",),
    )

    assert claim.to_json_dict() == {
        "id": "claim-1",
        "claim": "Product supports refunds",
        "questions": ["Does it support refunds?"],
    }


def test_payload_serializes_without_prompt_variant() -> None:
    claim = DraftClaimCompactionPromptClaim(
        claim_id="claim-1",
        claim="Product supports refunds",
        questions=(),
    )

    payload = DraftClaimCompactionPromptPayload(
        claims=(claim,),
        prompt_variant="draft_vs_draft",
    )

    assert payload.to_json_dict() == {"claims": [claim.to_json_dict()]}


def test_output_claim_rejects_invalid_claim_kind() -> None:
    with pytest.raises(ValueError, match="claim_kind"):
        DraftClaimCompactionOutputClaim(
            key="refunds",
            claim="Product supports refunds",
            claim_kind="unsupported",
            source_claim_refs=("claim-1",),
            triples=(),
            merge_decision="unmerged",
        )


def test_output_claim_rejects_invalid_merge_decision() -> None:
    with pytest.raises(ValueError, match="merge_decision"):
        DraftClaimCompactionOutputClaim(
            key="refunds",
            claim="Product supports refunds",
            claim_kind="capability",
            source_claim_refs=("claim-1",),
            triples=(),
            merge_decision="maybe",
        )


def test_triple_rejects_invalid_predicate() -> None:
    with pytest.raises(ValueError, match="predicate"):
        DraftClaimCompactionTriple(
            subject="Product",
            predicate="unknown",
            object="refunds",
            qualifiers=(),
        )


def _triple() -> DraftClaimCompactionTriple:
    return DraftClaimCompactionTriple(
        subject="Product",
        predicate="has_capability",
        object="refunds",
        qualifiers=("public policy",),
    )


def test_reduced_input_claim_serializes_key_claim_triples_only() -> None:
    claim = DraftClaimReducedRewriteInputClaim(
        key="refund_support",
        claim="Product supports refunds.",
        triples=(_triple(),),
    )

    assert claim.to_json_dict() == {
        "key": "refund_support",
        "claim": "Product supports refunds.",
        "triples": [_triple().to_json_dict()],
    }


def test_reduced_payload_serializes_compacted_claims_only() -> None:
    claim = DraftClaimReducedRewriteInputClaim(
        key="refund_support",
        claim="Product supports refunds.",
        triples=(_triple(),),
    )
    payload = DraftClaimReducedRewritePayload(compacted_claims=(claim,))

    assert payload.to_json_dict() == {
        "compacted_claims": [claim.to_json_dict()],
    }


def test_reduced_output_serializes_key_claim_triples_only() -> None:
    output = DraftClaimReducedRewriteOutput(
        key="refund_support",
        claim="Product supports refunds.",
        triples=(_triple(),),
    )

    assert output.to_json_dict() == {
        "key": "refund_support",
        "claim": "Product supports refunds.",
        "triples": [_triple().to_json_dict()],
    }
