from __future__ import annotations

from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_models import (
    DraftClaimForCompaction,
)
from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_prompt_contract import (
    DraftClaimCompactionOutputClaim,
    DraftClaimCompactionTriple,
)
from src.contexts.knowledge_workbench.extraction.application.policies.draft_claim_compaction_prompt_payload_builder import (
    DraftClaimCompactionPromptPayloadBuilder,
)


def _claim(
    ref: str,
    *,
    questions: tuple[str, ...] = ("What is it?",),
    exclusion_scope: tuple[str, ...] = ("pricing",),
) -> DraftClaimForCompaction:
    return DraftClaimForCompaction(
        observation_ref=ref,
        embedding_ref=f"embedding:{ref}",
        workflow_run_id="workflow-1",
        source_document_ref="document-1",
        source_unit_ref=f"unit:{ref}",
        claim=f"Claim text {ref}",
        possible_questions=questions,
        exclusion_scope=exclusion_scope,
        granularity="atomic",
        embedding_text=f"Claim text {ref}\nevidence_block: source",
        embedding_model_id="openai/gpt-oss-120b",
        dimensions=2,
        vector=(1.0, 0.0),
    )


def test_build_draft_vs_draft_payload_uses_observation_ref_as_id() -> None:
    payload = DraftClaimCompactionPromptPayloadBuilder().build_draft_vs_draft_payload(
        (_claim("claim-a"),),
    )

    assert payload.prompt_variant == "draft_vs_draft"
    assert payload.to_json_dict()["claims"][0]["id"] == "claim-a"


def test_build_draft_vs_draft_payload_preserves_input_order() -> None:
    payload = DraftClaimCompactionPromptPayloadBuilder().build_draft_vs_draft_payload(
        (_claim("claim-a"), _claim("claim-b"), _claim("claim-c")),
    )

    assert [claim["id"] for claim in payload.to_json_dict()["claims"]] == [
        "claim-a",
        "claim-b",
        "claim-c",
    ]


def test_build_draft_vs_draft_payload_includes_only_minimal_semantic_fields() -> None:
    payload = DraftClaimCompactionPromptPayloadBuilder().build_draft_vs_draft_payload(
        (_claim("claim-a"),),
    )

    claim_json = payload.to_json_dict()["claims"][0]

    assert claim_json == {
        "id": "claim-a",
        "claim": "Claim text claim-a",
        "questions": ["What is it?"],
        "exclusion_scope": ["pricing"],
        "granularity": "atomic",
    }
    assert "evidence_block" not in claim_json
    assert "source_unit_ref" not in claim_json
    assert "provenance" not in claim_json


def test_build_draft_vs_draft_payload_deduplicates_lists_preserving_order() -> None:
    payload = DraftClaimCompactionPromptPayloadBuilder().build_draft_vs_draft_payload(
        (
            _claim(
                "claim-a",
                questions=("What is it?", "What is it?", "How does it work?"),
                exclusion_scope=("pricing", "pricing", "delivery"),
            ),
        ),
    )

    claim_json = payload.to_json_dict()["claims"][0]

    assert claim_json["questions"] == ["What is it?", "How does it work?"]
    assert claim_json["exclusion_scope"] == ["pricing", "delivery"]


def _triple() -> DraftClaimCompactionTriple:
    return DraftClaimCompactionTriple(
        subject="Product",
        predicate="has_capability",
        object="refunds",
        qualifiers=(),
    )


def _compacted_claim(key: str) -> DraftClaimCompactionOutputClaim:
    return DraftClaimCompactionOutputClaim(
        key=key,
        claim=f"Claim {key}",
        claim_kind="capability",
        granularity="atomic",
        source_claim_refs=(f"source-{key}",),
        triples=(_triple(),),
        merge_decision="unmerged",
    )


def test_build_reduced_rewrite_payload_drops_full_compaction_fields() -> None:
    payload = DraftClaimCompactionPromptPayloadBuilder().build_reduced_rewrite_payload(
        (_compacted_claim("beta"), _compacted_claim("alpha")),
    )

    payload_json = payload.to_json_dict()

    assert [claim["key"] for claim in payload_json["compacted_claims"]] == [
        "alpha",
        "beta",
    ]
    claim_json = payload_json["compacted_claims"][0]
    assert claim_json == {
        "key": "alpha",
        "claim": "Claim alpha",
        "triples": [_triple().to_json_dict()],
    }
    assert "source_claim_refs" not in claim_json
    assert "merge_decision" not in claim_json
    assert "claim_kind" not in claim_json
    assert "granularity" not in claim_json
    assert "kind" not in claim_json
