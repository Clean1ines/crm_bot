from __future__ import annotations

from src.domain.runtime.evidence import (
    EvidenceFreshness,
    EvidenceItem,
    EvidenceScope,
    EvidenceSourceType,
)
from src.domain.runtime.source_authority import (
    SourceAuthorityPolicy,
    SourceConflictStrategy,
)


def test_source_authority_prefers_live_crm_over_compiled_price_list() -> None:
    document_price = EvidenceItem(
        source_type=EvidenceSourceType.COMPILED_PRICE_LIST,
        content="Price list says installation costs 5000 RUB.",
        scope=EvidenceScope.DOCUMENT,
        fact_key="price:installation",
        freshness=EvidenceFreshness.SNAPSHOT,
    )
    crm_price = EvidenceItem(
        source_type=EvidenceSourceType.CRM_OPERATIONAL,
        content="CRM says current installation price is 5500 RUB.",
        scope=EvidenceScope.CUSTOMER,
        fact_key="price:installation",
        freshness=EvidenceFreshness.LIVE,
    )

    decision = SourceAuthorityPolicy().select_preferred((document_price, crm_price))

    assert decision.preferred == crm_price
    assert decision.rejected == (document_price,)
    assert decision.conflict_detected


def test_source_authority_can_require_human_review_on_conflict() -> None:
    first_manager = EvidenceItem(
        source_type=EvidenceSourceType.MANAGER_OVERRIDE,
        content="Manager says price is 5000 RUB.",
        scope=EvidenceScope.THREAD,
        fact_key="price:installation",
        freshness=EvidenceFreshness.CURRENT,
    )
    second_manager = EvidenceItem(
        source_type=EvidenceSourceType.MANAGER_OVERRIDE,
        content="Manager says price is 5500 RUB.",
        scope=EvidenceScope.THREAD,
        fact_key="price:installation",
        freshness=EvidenceFreshness.CURRENT,
    )

    decision = SourceAuthorityPolicy().select_preferred(
        (first_manager, second_manager),
        strategy=SourceConflictStrategy.REQUIRE_HUMAN_REVIEW,
    )

    assert decision.conflict_detected
    assert decision.requires_human_review
    assert decision.preferred == first_manager or decision.preferred == second_manager


def test_source_authority_rejects_llm_only_bundle() -> None:
    llm_guess = EvidenceItem(
        source_type=EvidenceSourceType.LLM_REASONING,
        content="The model guessed the price.",
        scope=EvidenceScope.SYSTEM,
        fact_key="price:installation",
    )

    decision = SourceAuthorityPolicy().select_preferred((llm_guess,))

    assert decision.preferred is None
    assert decision.requires_human_review
    assert decision.reason == "no_authoritative_evidence"
