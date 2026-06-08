from __future__ import annotations

from pathlib import Path

import pytest

from src.contexts.knowledge_workbench.extraction.application.policies.empty_draft_claims_confirmation_policy import (
    EmptyDraftClaimsConfirmationDecision,
    EmptyDraftClaimsConfirmationInput,
    EmptyDraftClaimsConfirmationPolicy,
    EmptyDraftClaimsDecisionKind,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_ref import (
    SourceUnitRef,
)


ROOT = Path(__file__).resolve().parents[6]
POLICY_FILE = (
    ROOT
    / "src"
    / "contexts"
    / "knowledge_workbench"
    / "extraction"
    / "application"
    / "policies"
    / "empty_draft_claims_confirmation_policy.py"
)


def _input(
    *,
    previous_empty_claims_count: int,
    alternate_routes_available: bool,
    prompt_id: str = "faq_claim_observations",
) -> EmptyDraftClaimsConfirmationInput:
    return EmptyDraftClaimsConfirmationInput(
        source_unit_ref=SourceUnitRef("document-1.unit.0"),
        prompt_id=prompt_id,
        previous_empty_claims_count=previous_empty_claims_count,
        alternate_routes_available=alternate_routes_available,
    )


def _decide(
    *,
    previous_empty_claims_count: int,
    alternate_routes_available: bool,
) -> EmptyDraftClaimsConfirmationDecision:
    return EmptyDraftClaimsConfirmationPolicy().decide(
        _input(
            previous_empty_claims_count=previous_empty_claims_count,
            alternate_routes_available=alternate_routes_available,
        )
    )


def test_first_empty_with_alternate_route_tries_alternate_route() -> None:
    decision = _decide(
        previous_empty_claims_count=0,
        alternate_routes_available=True,
    )

    assert decision.kind is EmptyDraftClaimsDecisionKind.TRY_ALTERNATE_ROUTE


def test_second_empty_with_alternate_route_accepts_empty_claims() -> None:
    decision = _decide(
        previous_empty_claims_count=1,
        alternate_routes_available=True,
    )

    assert decision.kind is EmptyDraftClaimsDecisionKind.ACCEPT_EMPTY_CLAIMS


def test_later_empty_with_alternate_route_accepts_empty_claims() -> None:
    decision = _decide(
        previous_empty_claims_count=2,
        alternate_routes_available=True,
    )

    assert decision.kind is EmptyDraftClaimsDecisionKind.ACCEPT_EMPTY_CLAIMS


def test_first_empty_with_no_alternate_route_accepts_empty_claims() -> None:
    decision = _decide(
        previous_empty_claims_count=0,
        alternate_routes_available=False,
    )

    assert decision.kind is EmptyDraftClaimsDecisionKind.ACCEPT_EMPTY_CLAIMS


def test_negative_count_rejected() -> None:
    with pytest.raises(ValueError):
        _input(
            previous_empty_claims_count=-1,
            alternate_routes_available=True,
        )


def test_empty_prompt_id_rejected() -> None:
    with pytest.raises(ValueError):
        _input(
            previous_empty_claims_count=0,
            alternate_routes_available=True,
            prompt_id=" ",
        )


def test_policy_imports_no_provider_infrastructure() -> None:
    text = POLICY_FILE.read_text(encoding="utf-8")

    forbidden_markers = (
        "provider",
        "llm_runtime",
        "Groq",
        "groq",
        "Qwen",
        "qwen",
        "Postgres",
        "postgres",
        "PipelineArtifact",
        "artifact_runtime",
        "Ontology",
        "ClaimType",
        "ClaimTriple",
        "ClaimRelation",
        "Surface",
        "surface",
        ".commit(",
        ".rollback(",
    )

    offenders = [marker for marker in forbidden_markers if marker in text]

    assert not offenders
