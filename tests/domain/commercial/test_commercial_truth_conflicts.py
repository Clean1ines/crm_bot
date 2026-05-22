from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from src.domain.commercial.commercial_truth import (
    CommercialConflictResolutionStatus,
    CommercialFactSnapshot,
    CommercialSourceAuthority,
    CommercialSourceDescriptor,
    CommercialSourceKind,
    CommercialTruthResolutionPolicy,
    commercial_retrieval_surface_facts,
    default_commercial_source_authority,
    detect_commercial_fact_conflicts,
    resolve_commercial_conflict_by_policy,
)
from src.domain.commercial.price_knowledge import (
    PriceCondition,
    PriceFactStatus,
    PriceRange,
    PriceSourceRef,
    PriceValueKind,
    PublishedPriceFact,
)
from src.domain.commercial.pricing import MoneyAmount


def _source_ref() -> PriceSourceRef:
    return PriceSourceRef(
        price_document_id="price-doc-1",
        source_unit_id="unit-1",
        quote="Pro — 2490 ₽/мес.",
    )


def _fact(
    *,
    fact_id: str,
    item_name: str = "Pro",
    amount: str = "2490",
    currency: str = "RUB",
    value_kind: PriceValueKind = PriceValueKind.EXACT,
    unit: str = "month",
    variant: dict[str, str] | None = None,
    status: PriceFactStatus = PriceFactStatus.PUBLISHED,
    price_text: str = "",
    conditions: tuple[PriceCondition, ...] = (),
) -> PublishedPriceFact:
    money = (
        None
        if value_kind == PriceValueKind.ON_REQUEST
        else MoneyAmount.from_text(amount, currency)
    )
    return PublishedPriceFact(
        id=fact_id,
        project_id="project-1",
        price_document_id=f"price-doc-{fact_id}",
        item_name=item_name,
        value_kind=value_kind,
        amount=money,
        unit=unit,
        variant=variant or {"period": "monthly"},
        status=status,
        price_text=price_text,
        conditions=conditions,
        source_refs=(_source_ref(),),
        confidence=Decimal("0.9"),
    )


def _range_fact(
    *,
    fact_id: str,
    min_amount: str = "2000",
    max_amount: str = "3000",
) -> PublishedPriceFact:
    return PublishedPriceFact(
        id=fact_id,
        project_id="project-1",
        price_document_id=f"price-doc-{fact_id}",
        item_name="Pro",
        value_kind=PriceValueKind.RANGE,
        price_range=PriceRange(
            min_amount=MoneyAmount.from_text(min_amount, "RUB"),
            max_amount=MoneyAmount.from_text(max_amount, "RUB"),
        ),
        unit="month",
        variant={"period": "monthly"},
        status=PriceFactStatus.PUBLISHED,
        source_refs=(_source_ref(),),
        confidence=Decimal("0.9"),
    )


def _source(
    *,
    source_id: str,
    kind: CommercialSourceKind,
    observed_at: datetime | None = None,
    authority: CommercialSourceAuthority | None = None,
) -> CommercialSourceDescriptor:
    return CommercialSourceDescriptor(
        id=source_id,
        kind=kind,
        authority=authority,
        observed_at=observed_at,
    )


def _snapshot(
    fact: PublishedPriceFact,
    *,
    source_id: str,
    kind: CommercialSourceKind,
    observed_at: datetime | None = None,
    authority: CommercialSourceAuthority | None = None,
) -> CommercialFactSnapshot:
    return CommercialFactSnapshot(
        fact=fact,
        source=_source(
            source_id=source_id,
            kind=kind,
            observed_at=observed_at,
            authority=authority,
        ),
    )


def test_source_kind_defaults_to_expected_authority_layers() -> None:
    assert (
        default_commercial_source_authority(CommercialSourceKind.LIVE_CRM)
        == CommercialSourceAuthority.LIVE
    )
    assert (
        default_commercial_source_authority(CommercialSourceKind.STRUCTURED_PRICE_LIST)
        == CommercialSourceAuthority.PRIMARY
    )
    assert (
        default_commercial_source_authority(CommercialSourceKind.FAQ)
        == CommercialSourceAuthority.SUPPORTING
    )


def test_same_commercial_value_across_sources_is_not_conflict() -> None:
    price_list_fact = _fact(fact_id="fact-price-list", amount="2490")
    faq_fact = _fact(fact_id="fact-faq", amount="2490")

    conflicts = detect_commercial_fact_conflicts(
        (
            _snapshot(
                price_list_fact,
                source_id="prices-may",
                kind=CommercialSourceKind.STRUCTURED_PRICE_LIST,
            ),
            _snapshot(
                faq_fact,
                source_id="faq-old",
                kind=CommercialSourceKind.FAQ,
            ),
        )
    )

    assert conflicts == ()


def test_detects_price_conflict_for_same_identity_with_different_values() -> None:
    left = _fact(fact_id="fact-left", amount="2490")
    right = _fact(fact_id="fact-right", amount="2990")

    conflicts = detect_commercial_fact_conflicts(
        (
            _snapshot(
                left,
                source_id="prices-may",
                kind=CommercialSourceKind.STRUCTURED_PRICE_LIST,
            ),
            _snapshot(
                right,
                source_id="faq-old",
                kind=CommercialSourceKind.FAQ,
            ),
        )
    )

    assert len(conflicts) == 1
    assert conflicts[0].identity.normalized_item_name == "pro"
    assert conflicts[0].fact_ids == ("fact-left", "fact-right")


def test_detects_conflict_between_exact_range_and_on_request_values() -> None:
    exact = _fact(fact_id="fact-exact", amount="2490")
    price_range = _range_fact(fact_id="fact-range")

    conflicts = detect_commercial_fact_conflicts(
        (
            _snapshot(
                exact,
                source_id="prices",
                kind=CommercialSourceKind.STRUCTURED_PRICE_LIST,
            ),
            _snapshot(
                price_range,
                source_id="offer",
                kind=CommercialSourceKind.COMMERCIAL_OFFER,
            ),
        )
    )

    assert len(conflicts) == 1
    assert len(conflicts[0].value_signatures) == 2


def test_higher_authority_policy_selects_live_or_primary_source() -> None:
    faq = _fact(fact_id="fact-faq", amount="2990")
    price_list = _fact(fact_id="fact-price-list", amount="2490")
    conflict = detect_commercial_fact_conflicts(
        (
            _snapshot(faq, source_id="faq-old", kind=CommercialSourceKind.FAQ),
            _snapshot(
                price_list,
                source_id="prices-may",
                kind=CommercialSourceKind.STRUCTURED_PRICE_LIST,
            ),
        )
    )[0]

    resolution = resolve_commercial_conflict_by_policy(
        conflict,
        CommercialTruthResolutionPolicy.HIGHER_AUTHORITY_WINS,
    )

    assert resolution.status == CommercialConflictResolutionStatus.RESOLVED_BY_POLICY
    assert resolution.selected_snapshot is not None
    assert resolution.selected_snapshot.fact.id == "fact-price-list"
    assert resolution.reason == "higher_authority_source_selected"


def test_higher_authority_policy_requires_manual_review_on_same_authority_tie() -> None:
    left = _fact(fact_id="fact-left", amount="2490")
    right = _fact(fact_id="fact-right", amount="2990")
    conflict = detect_commercial_fact_conflicts(
        (
            _snapshot(
                left,
                source_id="prices-may",
                kind=CommercialSourceKind.STRUCTURED_PRICE_LIST,
            ),
            _snapshot(
                right,
                source_id="prices-june",
                kind=CommercialSourceKind.STRUCTURED_PRICE_LIST,
            ),
        )
    )[0]

    resolution = resolve_commercial_conflict_by_policy(
        conflict,
        CommercialTruthResolutionPolicy.HIGHER_AUTHORITY_WINS,
    )

    assert resolution.status == CommercialConflictResolutionStatus.UNRESOLVED
    assert resolution.selected_snapshot is None
    assert resolution.reason == "higher_authority_tie_requires_manual_review"


def test_newer_source_policy_selects_latest_source_when_policy_allows_it() -> None:
    older = _fact(fact_id="fact-older", amount="2490")
    newer = _fact(fact_id="fact-newer", amount="2990")
    conflict = detect_commercial_fact_conflicts(
        (
            _snapshot(
                older,
                source_id="prices-may",
                kind=CommercialSourceKind.STRUCTURED_PRICE_LIST,
                observed_at=datetime(2026, 5, 1, tzinfo=UTC),
            ),
            _snapshot(
                newer,
                source_id="prices-june",
                kind=CommercialSourceKind.STRUCTURED_PRICE_LIST,
                observed_at=datetime(2026, 6, 1, tzinfo=UTC),
            ),
        )
    )[0]

    resolution = resolve_commercial_conflict_by_policy(
        conflict,
        CommercialTruthResolutionPolicy.NEWER_SOURCE_WINS,
    )

    assert resolution.status == CommercialConflictResolutionStatus.RESOLVED_BY_POLICY
    assert resolution.selected_snapshot is not None
    assert resolution.selected_snapshot.fact.id == "fact-newer"


def test_manual_policy_blocks_conflicted_facts_from_runtime_surface() -> None:
    left = _fact(fact_id="fact-left", amount="2490")
    right = _fact(fact_id="fact-right", amount="2990")
    unrelated = _fact(
        fact_id="fact-unrelated",
        item_name="Enterprise",
        amount="9900",
    )

    surface = commercial_retrieval_surface_facts(
        (
            _snapshot(
                left,
                source_id="prices-may",
                kind=CommercialSourceKind.STRUCTURED_PRICE_LIST,
            ),
            _snapshot(
                right,
                source_id="faq-old",
                kind=CommercialSourceKind.FAQ,
            ),
            _snapshot(
                unrelated,
                source_id="prices-may",
                kind=CommercialSourceKind.STRUCTURED_PRICE_LIST,
            ),
        ),
        policy=CommercialTruthResolutionPolicy.MANUAL_REVIEW,
    )

    assert tuple(fact.id for fact in surface) == ("fact-unrelated",)


def test_runtime_surface_can_apply_higher_authority_resolution_policy() -> None:
    faq = _fact(fact_id="fact-faq", amount="2990")
    price_list = _fact(fact_id="fact-price-list", amount="2490")

    surface = commercial_retrieval_surface_facts(
        (
            _snapshot(faq, source_id="faq-old", kind=CommercialSourceKind.FAQ),
            _snapshot(
                price_list,
                source_id="prices-may",
                kind=CommercialSourceKind.STRUCTURED_PRICE_LIST,
            ),
        ),
        policy=CommercialTruthResolutionPolicy.HIGHER_AUTHORITY_WINS,
    )

    assert tuple(fact.id for fact in surface) == ("fact-price-list",)


def test_runtime_surface_never_includes_non_published_facts() -> None:
    draft = _fact(
        fact_id="fact-draft",
        amount="2490",
        status=PriceFactStatus.NEEDS_REVIEW,
    )

    surface = commercial_retrieval_surface_facts(
        (
            _snapshot(
                draft,
                source_id="prices-may",
                kind=CommercialSourceKind.STRUCTURED_PRICE_LIST,
            ),
        ),
        policy=CommercialTruthResolutionPolicy.MANUAL_REVIEW,
    )

    assert surface == ()


def test_condition_changes_are_treated_as_commercial_value_conflict() -> None:
    left = _fact(
        fact_id="fact-left",
        amount="2490",
        conditions=(PriceCondition("для новых клиентов"),),
    )
    right = _fact(
        fact_id="fact-right",
        amount="2490",
        conditions=(PriceCondition("для всех клиентов"),),
    )

    conflicts = detect_commercial_fact_conflicts(
        (
            _snapshot(
                left,
                source_id="prices-may",
                kind=CommercialSourceKind.STRUCTURED_PRICE_LIST,
            ),
            _snapshot(
                right,
                source_id="faq-old",
                kind=CommercialSourceKind.FAQ,
            ),
        )
    )

    assert len(conflicts) == 1
