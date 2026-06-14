from __future__ import annotations

import pytest

from src.contexts.knowledge_workbench.extraction.application.policies.draft_claim_compaction_output_validator import (
    DraftClaimCompactionOutputValidator,
    InvalidDraftClaimCompactionOutput,
)
from src.domain.project_plane.json_types import JsonObject


def _valid_payload() -> JsonObject:
    return {
        "compacted_claims": [
            {
                "key": "refund-support",
                "claim": "Product supports refunds.",
                "claim_kind": "capability",
                "granularity": "atomic",
                "source_claim_refs": ["claim-a", "claim-b"],
                "triples": [
                    {
                        "subject": "Product",
                        "predicate": "has_capability",
                        "object": "refunds",
                        "qualifiers": [],
                    }
                ],
                "merge_decision": "merged",
            },
            {
                "key": "delivery-limit",
                "claim": "Delivery has limits.",
                "claim_kind": "limitation",
                "granularity": "atomic",
                "source_claim_refs": ["claim-c"],
                "triples": [],
                "merge_decision": "unmerged",
            },
        ]
    }


def test_accepts_valid_compacted_output() -> None:
    output = DraftClaimCompactionOutputValidator().validate(
        payload=_valid_payload(),
        input_claim_refs=("claim-a", "claim-b", "claim-c"),
    )

    assert len(output.compacted_claims) == 2
    assert output.compacted_claims[0].source_claim_refs == ("claim-a", "claim-b")
    assert output.compacted_claims[1].triples == ()


def test_rejects_missing_compacted_claims() -> None:
    with pytest.raises(InvalidDraftClaimCompactionOutput, match="compacted_claims"):
        DraftClaimCompactionOutputValidator().validate(
            payload={},
            input_claim_refs=("claim-a",),
        )


@pytest.mark.parametrize(
    "field_name",
    [
        "questions",
        "exclusion_scope",
        "evidence",
        "mentions",
        "source_refs",
        "metrics",
        "warnings",
    ],
)
def test_rejects_forbidden_fields(field_name: str) -> None:
    payload = _valid_payload()
    payload["compacted_claims"][0][field_name] = []

    with pytest.raises(InvalidDraftClaimCompactionOutput, match=field_name):
        DraftClaimCompactionOutputValidator().validate(
            payload=payload,
            input_claim_refs=("claim-a", "claim-b", "claim-c"),
        )


def test_rejects_source_refs_outside_input_ids() -> None:
    payload = _valid_payload()
    payload["compacted_claims"][0]["source_claim_refs"] = ["claim-x", "claim-b"]

    with pytest.raises(InvalidDraftClaimCompactionOutput, match="input ids"):
        DraftClaimCompactionOutputValidator().validate(
            payload=payload,
            input_claim_refs=("claim-a", "claim-b", "claim-c"),
        )


def test_rejects_missing_input_ids() -> None:
    payload = _valid_payload()
    payload["compacted_claims"] = payload["compacted_claims"][:1]

    with pytest.raises(InvalidDraftClaimCompactionOutput, match="exactly once"):
        DraftClaimCompactionOutputValidator().validate(
            payload=payload,
            input_claim_refs=("claim-a", "claim-b", "claim-c"),
        )


def test_rejects_duplicated_input_ids() -> None:
    payload = _valid_payload()
    payload["compacted_claims"][1]["source_claim_refs"] = ["claim-a"]

    with pytest.raises(InvalidDraftClaimCompactionOutput, match="duplicated"):
        DraftClaimCompactionOutputValidator().validate(
            payload=payload,
            input_claim_refs=("claim-a", "claim-b", "claim-c"),
        )


def test_rejects_merge_decision_mismatch_for_single_source() -> None:
    payload = _valid_payload()
    payload["compacted_claims"][1]["merge_decision"] = "merged"

    with pytest.raises(InvalidDraftClaimCompactionOutput, match="unmerged"):
        DraftClaimCompactionOutputValidator().validate(
            payload=payload,
            input_claim_refs=("claim-a", "claim-b", "claim-c"),
        )


def test_rejects_merge_decision_mismatch_for_multiple_sources() -> None:
    payload = _valid_payload()
    payload["compacted_claims"][0]["merge_decision"] = "unmerged"

    with pytest.raises(InvalidDraftClaimCompactionOutput, match="merged"):
        DraftClaimCompactionOutputValidator().validate(
            payload=payload,
            input_claim_refs=("claim-a", "claim-b", "claim-c"),
        )


def test_rejects_invalid_predicate() -> None:
    payload = _valid_payload()
    payload["compacted_claims"][0]["triples"][0]["predicate"] = "causes"

    with pytest.raises(InvalidDraftClaimCompactionOutput, match="predicate"):
        DraftClaimCompactionOutputValidator().validate(
            payload=payload,
            input_claim_refs=("claim-a", "claim-b", "claim-c"),
        )


def test_accepts_empty_triples() -> None:
    payload = {
        "compacted_claims": [
            {
                "key": "refund-support",
                "claim": "Product supports refunds.",
                "claim_kind": "capability",
                "granularity": "atomic",
                "source_claim_refs": ["claim-a"],
                "triples": [],
                "merge_decision": "unmerged",
            }
        ]
    }

    output = DraftClaimCompactionOutputValidator().validate(
        payload=payload,
        input_claim_refs=("claim-a",),
    )

    assert output.compacted_claims[0].triples == ()
