from __future__ import annotations
from collections.abc import Mapping
from decimal import Decimal
from src.application.services.commercial_truth_review_service import (
    CommercialTruthReviewService,
    commercial_truth_fact_value_text,
    commercial_source_descriptor_from_price_document,
    commercial_source_kind_from_price_document,
)
from src.domain.commercial.commercial_truth import (
    CommercialConflictResolutionStatus,
    CommercialSourceDescriptor,
    CommercialSourceKind,
    CommercialTruthResolutionPolicy,
)
from src.domain.commercial.price_knowledge import (
    PriceDocument,
    PriceDocumentInputKind,
    PriceDocumentSourceFormat,
    PriceDocumentStatus,
    PriceFactStatus,
    PriceSourceRef,
    PriceValueKind,
    PublishedPriceFact,
)
from src.domain.commercial.pricing import MoneyAmount
from src.domain.project_plane.knowledge_views import KnowledgeDocumentDetailView


def _mapping_list(value: object) -> list[Mapping[str, object]]:
    assert isinstance(value, list)
    items: list[Mapping[str, object]] = []
    for item in value:
        assert isinstance(item, Mapping)
        items.append(item)
    return items


def _knowledge_document(
    *,
    preprocessing_mode: str | None,
    file_name: str = "prices.md",
    created_at: str = "2026-05-01T12:30:00+00:00",
) -> KnowledgeDocumentDetailView:
    return KnowledgeDocumentDetailView(
        id="knowledge-doc-1",
        project_id="project-1",
        file_name=file_name,
        file_size=1024,
        status="processed",
        error=None,
        uploaded_by=None,
        created_at=created_at,
        updated_at=created_at,
        source_unit_count=1,
        preprocessing_mode=preprocessing_mode,
    )


def _source_ref() -> PriceSourceRef:
    return PriceSourceRef(
        price_document_id="price-doc-1",
        source_unit_id="unit-1",
        quote="Pro — 2490 ₽/мес.",
    )


def _fact(
    *,
    fact_id: str,
    amount: str,
    item_name: str = "Pro",
    price_document_id: str | None = None,
    status: PriceFactStatus = PriceFactStatus.PUBLISHED,
) -> PublishedPriceFact:
    return PublishedPriceFact(
        id=fact_id,
        project_id="project-1",
        price_document_id=price_document_id or f"price-doc-{fact_id}",
        item_name=item_name,
        value_kind=PriceValueKind.EXACT,
        amount=MoneyAmount.from_text(amount, "RUB"),
        unit="month",
        variant={"period": "monthly"},
        status=status,
        source_refs=(_source_ref(),),
        confidence=Decimal("0.9"),
    )


def _source(source_id: str, kind: CommercialSourceKind) -> CommercialSourceDescriptor:
    return CommercialSourceDescriptor(id=source_id, kind=kind, title=source_id)


def test_review_report_returns_surface_for_non_conflicting_published_facts() -> None:
    fact = _fact(fact_id="pro", amount="2490")
    report = CommercialTruthReviewService().review_price_facts(
        facts=(fact,),
        sources_by_price_document_id={
            fact.price_document_id: _source(
                "prices-may", CommercialSourceKind.STRUCTURED_PRICE_LIST
            )
        },
    )
    assert report.fact_count == 1
    assert report.conflict_count == 0
    assert report.surface_fact_ids == ("pro",)
    assert report.facts[0].source_kind == "structured_price_list"
    assert report.facts[0].source_authority == "primary"


def test_review_report_blocks_conflicted_facts_under_manual_policy() -> None:
    price_list = _fact(fact_id="price-list", amount="2490")
    faq = _fact(fact_id="faq", amount="2990")
    report = CommercialTruthReviewService().review_price_facts(
        facts=(price_list, faq),
        sources_by_price_document_id={
            price_list.price_document_id: _source(
                "prices-may", CommercialSourceKind.STRUCTURED_PRICE_LIST
            ),
            faq.price_document_id: _source("faq-old", CommercialSourceKind.FAQ),
        },
        policy=CommercialTruthResolutionPolicy.MANUAL_REVIEW,
    )
    assert report.conflict_count == 1
    assert report.unresolved_conflict_count == 1
    assert report.resolved_conflict_count == 0
    assert report.surface_fact_ids == ()
    assert (
        report.conflicts[0].resolution_status
        == CommercialConflictResolutionStatus.UNRESOLVED.value
    )
    assert tuple((option.fact_id for option in report.conflicts[0].options)) == (
        "price-list",
        "faq",
    )


def test_review_report_can_preview_higher_authority_resolution_surface() -> None:
    price_list = _fact(fact_id="price-list", amount="2490")
    faq = _fact(fact_id="faq", amount="2990")
    report = CommercialTruthReviewService().review_price_facts(
        facts=(faq, price_list),
        sources_by_price_document_id={
            price_list.price_document_id: _source(
                "prices-may", CommercialSourceKind.STRUCTURED_PRICE_LIST
            ),
            faq.price_document_id: _source("faq-old", CommercialSourceKind.FAQ),
        },
        policy=CommercialTruthResolutionPolicy.HIGHER_AUTHORITY_WINS,
    )
    assert report.conflict_count == 1
    assert report.resolved_conflict_count == 1
    assert report.unresolved_conflict_count == 0
    assert report.conflicts[0].selected_fact_id == "price-list"
    assert report.surface_fact_ids == ("price-list",)


def test_review_report_excludes_non_runtime_facts_from_surface() -> None:
    draft = _fact(fact_id="draft", amount="2490", status=PriceFactStatus.NEEDS_REVIEW)
    report = CommercialTruthReviewService().review_price_facts(
        facts=(draft,),
        sources_by_price_document_id={
            draft.price_document_id: _source(
                "prices-may", CommercialSourceKind.STRUCTURED_PRICE_LIST
            )
        },
    )
    assert report.fact_count == 1
    assert report.conflict_count == 0
    assert report.surface_fact_ids == ()
    assert report.facts[0].is_runtime_eligible is False


def test_review_report_uses_unknown_source_when_source_metadata_is_missing() -> None:
    fact = _fact(fact_id="pro", amount="2490")
    report = CommercialTruthReviewService().review_price_facts(
        facts=(fact,), sources_by_price_document_id={}
    )
    assert report.facts[0].source_id == fact.price_document_id
    assert report.facts[0].source_kind == "unknown"
    assert report.facts[0].source_authority == "unknown"


def test_review_report_serializes_compact_payload_for_future_read_side() -> None:
    price_list = _fact(fact_id="price-list", amount="2490")
    faq = _fact(fact_id="faq", amount="2990")
    report = CommercialTruthReviewService().review_price_facts(
        facts=(price_list, faq),
        sources_by_price_document_id={
            price_list.price_document_id: _source(
                "prices-may", CommercialSourceKind.STRUCTURED_PRICE_LIST
            ),
            faq.price_document_id: _source("faq-old", CommercialSourceKind.FAQ),
        },
    )
    payload = report.to_dict()
    assert payload["policy"] == "manual_review"
    assert payload["fact_count"] == 2
    assert payload["conflict_count"] == 1
    assert payload["surface_fact_ids"] == []
    assert payload["conflicts"]


def test_source_kind_from_price_document_classifies_table_price_lists_as_primary() -> (
    None
):
    document = PriceDocument(
        id="price-doc-1",
        project_id="project-1",
        knowledge_document_id="knowledge-doc-1",
        source_format=PriceDocumentSourceFormat.CSV,
        input_kind=PriceDocumentInputKind.TABLE,
        status=PriceDocumentStatus.READY,
    )
    source_kind = commercial_source_kind_from_price_document(document)
    descriptor = commercial_source_descriptor_from_price_document(document)
    assert source_kind == CommercialSourceKind.STRUCTURED_PRICE_LIST
    assert descriptor.id == "price-doc-1"
    assert descriptor.kind == CommercialSourceKind.STRUCTURED_PRICE_LIST
    assert descriptor.effective_authority.value == "primary"


def test_source_kind_from_price_document_classifies_non_table_commercial_text_conservatively() -> (
    None
):
    document = PriceDocument(
        id="price-doc-1",
        project_id="project-1",
        knowledge_document_id="knowledge-doc-1",
        source_format=PriceDocumentSourceFormat.MARKDOWN,
        input_kind=PriceDocumentInputKind.MIXED,
        status=PriceDocumentStatus.READY,
    )
    assert (
        commercial_source_kind_from_price_document(document)
        == CommercialSourceKind.COMMERCIAL_OFFER
    )


def test_source_kind_from_price_document_keeps_unknown_when_format_is_unknown() -> None:
    document = PriceDocument(
        id="price-doc-1",
        project_id="project-1",
        knowledge_document_id="knowledge-doc-1",
        source_format=PriceDocumentSourceFormat.UNKNOWN,
        input_kind=PriceDocumentInputKind.UNKNOWN,
        status=PriceDocumentStatus.READY,
    )
    assert (
        commercial_source_kind_from_price_document(document)
        == CommercialSourceKind.UNKNOWN
    )


def test_review_fact_dto_includes_value_text_and_source_quote() -> None:
    fact = _fact(fact_id="pro", amount="2490")
    report = CommercialTruthReviewService().review_price_facts(
        facts=(fact,),
        sources_by_price_document_id={
            fact.price_document_id: _source(
                "prices-may", CommercialSourceKind.STRUCTURED_PRICE_LIST
            )
        },
    )
    payload = report.to_dict()
    facts_payload = _mapping_list(payload["facts"])
    assert report.facts[0].value_text == "2490 RUB"
    assert report.facts[0].source_quote == "Pro — 2490 ₽/мес."
    assert facts_payload[0]["value_text"] == "2490 RUB"
    assert facts_payload[0]["source_quote"] == "Pro — 2490 ₽/мес."


def test_review_conflict_options_include_value_text_and_source_quote() -> None:
    price_list = _fact(fact_id="price-list", amount="2490")
    faq = _fact(fact_id="faq", amount="2990")
    report = CommercialTruthReviewService().review_price_facts(
        facts=(price_list, faq),
        sources_by_price_document_id={
            price_list.price_document_id: _source(
                "prices-may", CommercialSourceKind.STRUCTURED_PRICE_LIST
            ),
            faq.price_document_id: _source("faq-old", CommercialSourceKind.FAQ),
        },
    )
    payload = report.to_dict()
    conflicts_payload = _mapping_list(payload["conflicts"])
    conflict = conflicts_payload[0]
    options_payload = _mapping_list(conflict["options"])
    assert options_payload[0]["value_text"] == "2490 RUB"
    assert options_payload[1]["value_text"] == "2990 RUB"
    assert options_payload[0]["source_quote"] == "Pro — 2490 ₽/мес."


def test_commercial_truth_fact_value_text_handles_on_request_price_text() -> None:
    fact = PublishedPriceFact(
        id="on-request",
        project_id="project-1",
        price_document_id="price-doc-on-request",
        item_name="Enterprise",
        value_kind=PriceValueKind.ON_REQUEST,
        unit="contract",
        status=PriceFactStatus.PUBLISHED,
        price_text="Цена рассчитывается индивидуально.",
        source_refs=(_source_ref(),),
        confidence=Decimal("0.9"),
    )
    assert (
        commercial_truth_fact_value_text(fact) == "Цена рассчитывается индивидуально."
    )


def test_review_report_serializes_surface_fact_reviews() -> None:
    fact = _fact(fact_id="pro", amount="2490")
    report = CommercialTruthReviewService().review_price_facts(
        facts=(fact,),
        sources_by_price_document_id={
            fact.price_document_id: _source(
                "prices-may", CommercialSourceKind.STRUCTURED_PRICE_LIST
            )
        },
    )
    payload = report.to_dict()
    surface_payload = _mapping_list(payload["surface_facts"])
    assert report.surface_fact_ids == ("pro",)
    assert tuple((item.fact_id for item in report.surface_fact_reviews)) == ("pro",)
    assert surface_payload[0]["fact_id"] == "pro"
    assert surface_payload[0]["value_text"] == "2490 RUB"
    assert surface_payload[0]["source_quote"] == "Pro — 2490 ₽/мес."


def test_review_report_surface_facts_stay_empty_for_unresolved_conflicts() -> None:
    price_list = _fact(fact_id="price-list", amount="2490")
    faq = _fact(fact_id="faq", amount="2990")
    report = CommercialTruthReviewService().review_price_facts(
        facts=(price_list, faq),
        sources_by_price_document_id={
            price_list.price_document_id: _source(
                "prices-may", CommercialSourceKind.STRUCTURED_PRICE_LIST
            ),
            faq.price_document_id: _source("faq-old", CommercialSourceKind.FAQ),
        },
        policy=CommercialTruthResolutionPolicy.MANUAL_REVIEW,
    )
    payload = report.to_dict()
    assert report.surface_fact_ids == ()
    assert report.surface_fact_reviews == ()
    assert payload["surface_facts"] == []


def test_source_kind_prefers_price_list_preprocessing_mode_over_fallback_shape() -> (
    None
):
    document = PriceDocument(
        id="price-doc-1",
        project_id="project-1",
        knowledge_document_id="knowledge-doc-1",
        source_format=PriceDocumentSourceFormat.MARKDOWN,
        input_kind=PriceDocumentInputKind.MIXED,
        status=PriceDocumentStatus.READY,
    )
    source_kind = commercial_source_kind_from_price_document(
        document,
        knowledge_document=_knowledge_document(preprocessing_mode="price_list"),
    )
    descriptor = commercial_source_descriptor_from_price_document(
        document,
        knowledge_document=_knowledge_document(preprocessing_mode="price_list"),
    )
    assert source_kind == CommercialSourceKind.STRUCTURED_PRICE_LIST
    assert descriptor.kind == CommercialSourceKind.STRUCTURED_PRICE_LIST
    assert descriptor.title == "prices.md"
    assert descriptor.observed_at is not None
    assert descriptor.observed_at.isoformat() == "2026-05-01T12:30:00+00:00"


def test_source_kind_classifies_faq_preprocessing_mode_as_supporting_faq() -> None:
    document = PriceDocument(
        id="price-doc-1",
        project_id="project-1",
        knowledge_document_id="knowledge-doc-1",
        source_format=PriceDocumentSourceFormat.MARKDOWN,
        input_kind=PriceDocumentInputKind.MIXED,
        status=PriceDocumentStatus.READY,
    )
    descriptor = commercial_source_descriptor_from_price_document(
        document,
        knowledge_document=_knowledge_document(
            preprocessing_mode="faq", file_name="faq.md"
        ),
    )
    assert descriptor.kind == CommercialSourceKind.FAQ
    assert descriptor.effective_authority.value == "supporting"
    assert descriptor.title == "faq.md"


def test_source_kind_keeps_price_document_fallback_without_knowledge_metadata() -> None:
    document = PriceDocument(
        id="price-doc-1",
        project_id="project-1",
        knowledge_document_id="knowledge-doc-1",
        source_format=PriceDocumentSourceFormat.CSV,
        input_kind=PriceDocumentInputKind.TABLE,
        status=PriceDocumentStatus.READY,
    )
    descriptor = commercial_source_descriptor_from_price_document(document)
    assert descriptor.kind == CommercialSourceKind.STRUCTURED_PRICE_LIST
    assert descriptor.title == "knowledge-doc-1"
    assert descriptor.observed_at is None


def test_source_descriptor_ignores_invalid_observed_at_without_failing_review() -> None:
    document = PriceDocument(
        id="price-doc-1",
        project_id="project-1",
        knowledge_document_id="knowledge-doc-1",
        source_format=PriceDocumentSourceFormat.UNKNOWN,
        input_kind=PriceDocumentInputKind.UNKNOWN,
        status=PriceDocumentStatus.READY,
    )
    descriptor = commercial_source_descriptor_from_price_document(
        document,
        knowledge_document=_knowledge_document(
            preprocessing_mode=None, created_at="not-a-date"
        ),
    )
    assert descriptor.kind == CommercialSourceKind.UNKNOWN
    assert descriptor.observed_at is None


def test_review_fact_dto_includes_source_title_and_observed_at() -> None:
    fact = _fact(fact_id="pro", amount="2490")
    price_document = PriceDocument(
        id=fact.price_document_id,
        project_id="project-1",
        knowledge_document_id="knowledge-doc-1",
        source_format=PriceDocumentSourceFormat.MARKDOWN,
        input_kind=PriceDocumentInputKind.MIXED,
        status=PriceDocumentStatus.READY,
    )
    descriptor = commercial_source_descriptor_from_price_document(
        price_document,
        knowledge_document=_knowledge_document(
            preprocessing_mode="price_list",
            file_name="prices_may.md",
            created_at="2026-05-01T12:30:00+00:00",
        ),
    )
    report = CommercialTruthReviewService().review_price_facts(
        facts=(fact,), sources_by_price_document_id={fact.price_document_id: descriptor}
    )
    payload = report.to_dict()
    facts_payload = _mapping_list(payload["facts"])
    surface_payload = _mapping_list(payload["surface_facts"])
    assert report.facts[0].source_title == "prices_may.md"
    assert report.facts[0].source_observed_at == "2026-05-01T12:30:00+00:00"
    assert facts_payload[0]["source_title"] == "prices_may.md"
    assert facts_payload[0]["source_observed_at"] == "2026-05-01T12:30:00+00:00"
    assert surface_payload[0]["source_title"] == "prices_may.md"
    assert surface_payload[0]["source_observed_at"] == "2026-05-01T12:30:00+00:00"
