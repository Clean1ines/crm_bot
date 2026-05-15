from __future__ import annotations

from pathlib import Path

from src.domain.commercial.price_query import (
    PriceQuery,
    PriceQueryIntent,
    PriceQueryResolution,
)
from src.domain.runtime.evidence import (
    EvidenceBundle,
    EvidenceFreshness,
    EvidenceItem,
    EvidenceScope,
    EvidenceSourceType,
)
from src.domain.runtime.evidence_plan import (
    EvidenceNeed,
    EvidenceNeedKind,
    EvidencePlan,
    EvidencePlanStatus,
)
from src.domain.runtime.source_authority import SourceConflictStrategy


def _evidence(
    source_type: EvidenceSourceType,
    *,
    content: str = "grounded fact",
    fact_key: str = "fact:key",
    freshness: EvidenceFreshness = EvidenceFreshness.SNAPSHOT,
) -> EvidenceItem:
    return EvidenceItem(
        source_type=source_type,
        content=content,
        scope=EvidenceScope.DOCUMENT,
        fact_key=fact_key,
        freshness=freshness,
    )


def test_faq_plan_requires_compiled_knowledge_and_can_proceed_with_it() -> None:
    plan = EvidencePlan.for_stable_faq()
    compiled_knowledge = _evidence(
        EvidenceSourceType.COMPILED_KNOWLEDGE,
        content="Refunds are reviewed by a manager.",
        fact_key="faq:refund",
    )

    decision = plan.decide(EvidenceBundle.from_items((compiled_knowledge,)))

    assert plan.required_source_types == (EvidenceSourceType.COMPILED_KNOWLEDGE,)
    assert not plan.requires_live_operational_source
    assert decision.status == EvidencePlanStatus.READY
    assert decision.answer_may_proceed
    assert decision.authority_decision is not None
    assert decision.authority_decision.preferred == compiled_knowledge


def test_direct_price_lookup_requires_compiled_price_list_and_rejects_llm_only() -> (
    None
):
    resolution = PriceQueryResolution(
        query=PriceQuery(
            intent=PriceQueryIntent.DIRECT_LOOKUP,
            item_name="installation",
        )
    )
    plan = EvidencePlan.for_price_query_resolution(resolution)
    llm_guess = _evidence(
        EvidenceSourceType.LLM_REASONING,
        content="The model guessed the price is 5000 RUB.",
        fact_key="price:installation",
    )

    decision = plan.decide(EvidenceBundle.from_items((llm_guess,)))

    assert plan.required_source_types == (EvidenceSourceType.COMPILED_PRICE_LIST,)
    assert not plan.requires_live_operational_source
    assert decision.status == EvidencePlanStatus.REQUIRES_HUMAN_REVIEW
    assert decision.requires_human_review
    assert not decision.answer_may_proceed
    assert decision.reason == "no_authoritative_evidence"


def test_personal_quote_requires_live_crm_operational_source() -> None:
    resolution = PriceQueryResolution(
        query=PriceQuery(
            intent=PriceQueryIntent.PERSONAL_QUOTE,
            item_name="installation",
            customer_id="client-1",
        )
    )
    plan = EvidencePlan.for_price_query_resolution(resolution)
    stale_snapshot = _evidence(
        EvidenceSourceType.COMPILED_PRICE_LIST,
        content="Snapshot price is 5000 RUB.",
        fact_key="price:installation",
    )

    missing_decision = plan.decide(EvidenceBundle.from_items((stale_snapshot,)))
    live_crm = _evidence(
        EvidenceSourceType.CRM_OPERATIONAL,
        content="Current personal quote is 5500 RUB.",
        fact_key="price:installation",
        freshness=EvidenceFreshness.LIVE,
    )
    ready_decision = plan.decide(EvidenceBundle.from_items((live_crm,)))

    assert plan.required_source_types == (EvidenceSourceType.CRM_OPERATIONAL,)
    assert plan.requires_live_operational_source
    assert missing_decision.requires_human_review
    assert missing_decision.reason == "missing_required_live_operational_evidence"
    assert ready_decision.answer_may_proceed


def test_availability_query_requires_live_catalog_or_crm_not_price_snapshot() -> None:
    resolution = PriceQueryResolution(
        query=PriceQuery(
            intent=PriceQueryIntent.AVAILABILITY_QUERY,
            item_name="business cards",
        )
    )
    plan = EvidencePlan.for_price_query_resolution(resolution)
    price_snapshot = _evidence(
        EvidenceSourceType.COMPILED_PRICE_LIST,
        content="Business cards cost 1800 RUB.",
        fact_key="availability:business cards",
    )

    missing_decision = plan.decide(EvidenceBundle.from_items((price_snapshot,)))
    live_catalog = _evidence(
        EvidenceSourceType.CATALOG_OPERATIONAL,
        content="Business cards are currently available.",
        fact_key="availability:business cards",
        freshness=EvidenceFreshness.LIVE,
    )
    ready_decision = plan.decide(EvidenceBundle.from_items((live_catalog,)))

    assert plan.required_source_types == (
        EvidenceSourceType.CATALOG_OPERATIONAL,
        EvidenceSourceType.CRM_OPERATIONAL,
    )
    assert missing_decision.requires_human_review
    assert ready_decision.answer_may_proceed


def test_missing_commercial_variant_slots_require_clarification_before_answer() -> None:
    resolution = PriceQueryResolution(
        query=PriceQuery(
            intent=PriceQueryIntent.VARIANT_LOOKUP,
            item_name="business cards",
            variant_filters={"quantity": "500"},
        ),
        missing_slots=("paper",),
        matched_offer_name="Business cards",
    )
    plan = EvidencePlan.for_price_query_resolution(resolution)
    compiled_price = _evidence(
        EvidenceSourceType.COMPILED_PRICE_LIST,
        content="500 business cards on standard paper cost 1800 RUB.",
        fact_key="price:business cards",
    )

    decision = plan.decide(EvidenceBundle.from_items((compiled_price,)))

    assert decision.status == EvidencePlanStatus.NEEDS_CLARIFICATION
    assert decision.needs_clarification
    assert decision.missing_slots == ("paper",)
    assert not decision.answer_may_proceed


def test_disambiguation_intent_requires_clarification_even_without_named_slots() -> (
    None
):
    resolution = PriceQueryResolution(
        query=PriceQuery(
            intent=PriceQueryIntent.DISAMBIGUATION_REQUIRED,
            item_name="cards",
        )
    )
    plan = EvidencePlan.for_price_query_resolution(resolution)
    compiled_price = _evidence(
        EvidenceSourceType.COMPILED_PRICE_LIST,
        content="Business cards and greeting cards have different prices.",
        fact_key="price:cards",
    )

    decision = plan.decide(EvidenceBundle.from_items((compiled_price,)))

    assert decision.status == EvidencePlanStatus.NEEDS_CLARIFICATION
    assert decision.needs_clarification
    assert decision.missing_slots == ()
    assert len(decision.missing_needs) == 1
    assert decision.missing_needs[0].kind == EvidenceNeedKind.CLARIFICATION
    assert decision.reason == "commercial_query_requires_clarification"
    assert not decision.answer_may_proceed


def test_live_evidence_need_requires_authoritative_source_even_when_fresh() -> None:
    need = EvidenceNeed(
        kind=EvidenceNeedKind.LIVE_OPERATIONAL,
        source_types=(EvidenceSourceType.LLM_REASONING,),
        requires_live_freshness=True,
    )
    live_llm_reasoning = _evidence(
        EvidenceSourceType.LLM_REASONING,
        content="The model claims the live availability is yes.",
        freshness=EvidenceFreshness.LIVE,
    )

    assert not need.is_satisfied_by(live_llm_reasoning)


def test_conflicting_authoritative_evidence_can_require_human_review() -> None:
    resolution = PriceQueryResolution(
        query=PriceQuery(
            intent=PriceQueryIntent.DIRECT_LOOKUP,
            item_name="installation",
        )
    )
    plan = EvidencePlan.for_price_query_resolution(
        resolution,
        conflict_strategy=SourceConflictStrategy.REQUIRE_HUMAN_REVIEW,
    )
    first_price = _evidence(
        EvidenceSourceType.COMPILED_PRICE_LIST,
        content="Installation costs 5000 RUB.",
        fact_key="price:installation",
    )
    second_price = _evidence(
        EvidenceSourceType.COMPILED_PRICE_LIST,
        content="Installation costs 5500 RUB.",
        fact_key="price:installation",
    )

    decision = plan.decide(EvidenceBundle.from_items((first_price, second_price)))

    assert decision.status == EvidencePlanStatus.REQUIRES_HUMAN_REVIEW
    assert decision.requires_human_review
    assert decision.authority_decision is not None
    assert decision.authority_decision.conflict_detected


def test_runtime_evidence_plan_domain_boundary_remains_clean() -> None:
    source = Path("src/domain/runtime/evidence_plan.py").read_text(encoding="utf-8")

    forbidden = (
        "fastapi",
        "starlette",
        "asyncpg",
        "redis",
        "httpx",
        "aiohttp",
        "telegram",
        "langchain",
        "langgraph",
        "src.infrastructure",
    )
    assert all(item not in source for item in forbidden)
