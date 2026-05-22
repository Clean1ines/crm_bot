from __future__ import annotations

from decimal import Decimal

import pytest

from src.domain.commercial.price_acquisition import (
    PriceAcquisitionCell,
    PriceAcquisitionFieldRole,
    PriceAcquisitionResult,
    PriceAcquisitionRow,
    PriceAcquisitionUnit,
    PriceColumnRoleCandidate,
    PriceCompilationIssue,
    PriceCompilationIssueCode,
    PriceCompilationIssueSeverity,
    PriceFactCandidate,
    PriceFactCandidateStatus,
    PriceFieldCandidate,
)
from src.domain.commercial.price_knowledge import (
    PriceCondition,
    PriceDocumentInputKind,
    PriceDocumentSourceFormat,
    PriceRange,
    PriceSourceRef,
    PriceValueKind,
)
from src.domain.commercial.pricing import MoneyAmount


def _source_ref() -> PriceSourceRef:
    return PriceSourceRef(
        price_document_id="price-doc-1",
        source_unit_id="unit-1",
        quote="Pro — 2490 ₽/мес.",
    )


def _unit() -> PriceAcquisitionUnit:
    return PriceAcquisitionUnit(
        id="unit-1",
        price_document_id="price-doc-1",
        source_index=0,
        source_format=PriceDocumentSourceFormat.MARKDOWN,
        input_kind=PriceDocumentInputKind.MIXED,
        raw_text="| service | price |\n| Pro | 2490 ₽/мес |",
        title="Тарифы",
    )


def test_acquisition_unit_supports_format_specific_metadata_without_runtime_leak() -> (
    None
):
    unit = PriceAcquisitionUnit(
        id="unit-1",
        price_document_id="price-doc-1",
        source_index=2,
        source_format=PriceDocumentSourceFormat.XLSX,
        input_kind=PriceDocumentInputKind.TABLE,
        raw_text="service,price\nPro,2490",
        metadata={"sheet": "main", "detected_header_row": 1},
    )

    assert unit.source_format == PriceDocumentSourceFormat.XLSX
    assert unit.input_kind == PriceDocumentInputKind.TABLE
    assert unit.metadata["sheet"] == "main"


def test_table_row_requires_cells_or_raw_cells_and_cell_row_match() -> None:
    cell = PriceAcquisitionCell(
        row_id="row-1",
        column_name="price",
        raw_value="2490 ₽/мес",
        normalized_value="2490 RUB month",
        role=PriceAcquisitionFieldRole.AMOUNT,
        confidence=Decimal("0.8"),
    )

    row = PriceAcquisitionRow(
        id="row-1",
        source_unit_id="unit-1",
        row_index=1,
        raw_cells={},
        cells=(cell,),
    )

    assert row.cells == (cell,)

    with pytest.raises(ValueError, match="raw_cells or cells"):
        PriceAcquisitionRow(
            id="row-2",
            source_unit_id="unit-1",
            row_index=2,
            raw_cells={},
        )


def test_column_role_candidate_must_be_explicit_confident_and_source_grounded() -> None:
    candidate = PriceColumnRoleCandidate(
        source_unit_id="unit-1",
        column_name="Цена",
        role=PriceAcquisitionFieldRole.AMOUNT,
        confidence=Decimal("0.75"),
        source_refs=(_source_ref(),),
        alternatives=(PriceAcquisitionFieldRole.PRICE_TEXT,),
    )

    assert candidate.role == PriceAcquisitionFieldRole.AMOUNT

    with pytest.raises(ValueError, match="source-grounded"):
        PriceColumnRoleCandidate(
            source_unit_id="unit-1",
            column_name="Цена",
            role=PriceAcquisitionFieldRole.AMOUNT,
            confidence=Decimal("0.75"),
            source_refs=(),
        )


def test_field_candidate_is_source_grounded_intermediate_fact_material() -> None:
    field = PriceFieldCandidate(
        role=PriceAcquisitionFieldRole.ITEM_NAME,
        value="Тариф Pro",
        normalized_value="pro",
        confidence=Decimal("0.9"),
        source_refs=(_source_ref(),),
    )

    assert field.normalized_value == "pro"


def test_exact_price_fact_candidate_is_needs_review_and_never_runtime_publishable() -> (
    None
):
    candidate = PriceFactCandidate(
        id="candidate-1",
        project_id="project-1",
        price_document_id="price-doc-1",
        item_name="Тариф Pro",
        value_kind=PriceValueKind.EXACT,
        amount=MoneyAmount.from_text("2490", "RUB"),
        unit="month",
        variant={"Period": "Monthly"},
        aliases=("pro",),
        conditions=(PriceCondition("для новых клиентов"),),
        source_refs=(_source_ref(),),
        confidence=Decimal("0.82"),
    )

    assert candidate.status == PriceFactCandidateStatus.NEEDS_REVIEW
    assert candidate.normalized_item_name == "тариф pro"
    assert candidate.normalized_variant == {"period": "monthly"}
    assert candidate.is_publishable_without_review is False


def test_price_fact_candidate_rejects_ungrounded_or_invalid_shapes() -> None:
    with pytest.raises(ValueError, match="source-grounded"):
        PriceFactCandidate(
            id="candidate-1",
            project_id="project-1",
            price_document_id="price-doc-1",
            item_name="Тариф Pro",
            value_kind=PriceValueKind.EXACT,
            amount=MoneyAmount.from_text("2490", "RUB"),
            unit="month",
            source_refs=(),
        )

    with pytest.raises(ValueError, match="requires price_range"):
        PriceFactCandidate(
            id="candidate-2",
            project_id="project-1",
            price_document_id="price-doc-1",
            item_name="Консалтинг",
            value_kind=PriceValueKind.RANGE,
            unit="project",
            source_refs=(_source_ref(),),
        )


def test_range_and_on_request_candidates_represent_non_exact_price_documents() -> None:
    range_candidate = PriceFactCandidate(
        id="candidate-range",
        project_id="project-1",
        price_document_id="price-doc-1",
        item_name="Консалтинг",
        value_kind=PriceValueKind.RANGE,
        price_range=PriceRange(
            min_amount=MoneyAmount.from_text("5000", "RUB"),
            max_amount=MoneyAmount.from_text("15000", "RUB"),
        ),
        unit="project",
        source_refs=(_source_ref(),),
    )
    on_request_candidate = PriceFactCandidate(
        id="candidate-custom",
        project_id="project-1",
        price_document_id="price-doc-1",
        item_name="Enterprise",
        value_kind=PriceValueKind.ON_REQUEST,
        unit="contract",
        price_text="Цена рассчитывается индивидуально.",
        source_refs=(_source_ref(),),
    )

    assert range_candidate.price_range is not None
    assert on_request_candidate.price_text == "Цена рассчитывается индивидуально."


def test_acquisition_result_links_units_rows_columns_candidates_and_issues() -> None:
    unit = _unit()
    row = PriceAcquisitionRow(
        id="row-1",
        source_unit_id=unit.id,
        row_index=1,
        raw_cells={"service": "Pro", "price": "2490"},
    )
    role = PriceColumnRoleCandidate(
        source_unit_id=unit.id,
        column_name="price",
        role=PriceAcquisitionFieldRole.AMOUNT,
        confidence=Decimal("0.8"),
        source_refs=(_source_ref(),),
    )
    candidate = PriceFactCandidate(
        id="candidate-1",
        project_id="project-1",
        price_document_id=unit.price_document_id,
        item_name="Pro",
        value_kind=PriceValueKind.EXACT,
        amount=MoneyAmount.from_text("2490", "RUB"),
        unit="month",
        source_refs=(_source_ref(),),
    )
    issue = PriceCompilationIssue(
        severity=PriceCompilationIssueSeverity.WARNING,
        code=PriceCompilationIssueCode.NEEDS_HUMAN_REVIEW,
        message="Several possible tariff variants were found.",
        source_refs=(_source_ref(),),
    )

    result = PriceAcquisitionResult(
        price_document_id=unit.price_document_id,
        source_format=PriceDocumentSourceFormat.MARKDOWN,
        input_kind=PriceDocumentInputKind.MIXED,
        units=(unit,),
        rows=(row,),
        column_roles=(role,),
        fact_candidates=(candidate,),
        issues=(issue,),
    )

    assert result.needs_review is True
    assert result.has_errors is False


def test_acquisition_result_rejects_rows_or_roles_detached_from_units() -> None:
    unit = _unit()

    with pytest.raises(ValueError, match="row must reference a known unit"):
        PriceAcquisitionResult(
            price_document_id=unit.price_document_id,
            source_format=PriceDocumentSourceFormat.MARKDOWN,
            input_kind=PriceDocumentInputKind.MIXED,
            units=(unit,),
            rows=(
                PriceAcquisitionRow(
                    id="row-1",
                    source_unit_id="missing-unit",
                    row_index=1,
                    raw_cells={"price": "2490"},
                ),
            ),
        )

    with pytest.raises(ValueError, match="column role must reference a known unit"):
        PriceAcquisitionResult(
            price_document_id=unit.price_document_id,
            source_format=PriceDocumentSourceFormat.MARKDOWN,
            input_kind=PriceDocumentInputKind.MIXED,
            units=(unit,),
            column_roles=(
                PriceColumnRoleCandidate(
                    source_unit_id="missing-unit",
                    column_name="price",
                    role=PriceAcquisitionFieldRole.AMOUNT,
                    confidence=Decimal("0.8"),
                    source_refs=(_source_ref(),),
                ),
            ),
        )
