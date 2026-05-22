from __future__ import annotations

from decimal import Decimal

import pytest

from src.domain.commercial.price_acquisition import (
    PriceAcquisitionFieldRole,
    PriceAcquisitionUnit,
    PriceCompilationIssueCode,
)
from src.domain.commercial.price_knowledge import (
    PriceDocumentInputKind,
    PriceDocumentSourceFormat,
    PriceValueKind,
)
from src.infrastructure.commercial_price.markdown_acquisition_adapter import (
    MarkdownPriceAcquisitionAdapter,
)


def _unit(raw_text: str) -> PriceAcquisitionUnit:
    return PriceAcquisitionUnit(
        id="unit-1",
        price_document_id="price-doc-1",
        source_index=0,
        source_format=PriceDocumentSourceFormat.MARKDOWN,
        input_kind=PriceDocumentInputKind.MIXED,
        raw_text=raw_text,
    )


@pytest.mark.asyncio
async def test_adapter_supports_markdown_and_markdown_like_text_tables() -> None:
    adapter = MarkdownPriceAcquisitionAdapter()

    assert adapter.supports(
        source_format=PriceDocumentSourceFormat.MARKDOWN,
        input_kind=PriceDocumentInputKind.MIXED,
    )
    assert adapter.supports(
        source_format=PriceDocumentSourceFormat.PLAIN_TEXT,
        input_kind=PriceDocumentInputKind.STRUCTURED_TEXT,
    )
    assert not adapter.supports(
        source_format=PriceDocumentSourceFormat.CSV,
        input_kind=PriceDocumentInputKind.TABLE,
    )


@pytest.mark.asyncio
async def test_adapter_extracts_rows_roles_fields_and_exact_fact_candidates() -> None:
    unit = _unit(
        """
| Тариф | Цена | Период |
| --- | --- | --- |
| Pro | 2490 ₽ | мес |
| Basic | 990 руб | мес |
""".strip()
    )

    result = await MarkdownPriceAcquisitionAdapter().acquire(
        project_id="project-1",
        price_document_id="price-doc-1",
        source_format=PriceDocumentSourceFormat.MARKDOWN,
        input_kind=PriceDocumentInputKind.MIXED,
        units=(unit,),
    )

    assert result.issues == ()
    assert len(result.rows) == 2
    assert {role.role for role in result.column_roles} >= {
        PriceAcquisitionFieldRole.ITEM_NAME,
        PriceAcquisitionFieldRole.AMOUNT,
        PriceAcquisitionFieldRole.UNIT,
    }
    assert any(
        field.role == PriceAcquisitionFieldRole.ITEM_NAME
        for field in result.field_candidates
    )
    assert len(result.fact_candidates) == 2

    first = result.fact_candidates[0]
    assert first.project_id == "project-1"
    assert first.price_document_id == "price-doc-1"
    assert first.item_name == "Pro"
    assert first.value_kind == PriceValueKind.EXACT
    assert first.amount is not None
    assert first.amount.amount == Decimal("2490")
    assert first.amount.currency == "RUB"
    assert first.unit == "мес"
    assert first.source_refs[0].source_row_id == result.rows[0].id


@pytest.mark.asyncio
async def test_adapter_extracts_starting_from_and_on_request_candidates() -> None:
    unit = _unit(
        """
| Услуга | Стоимость |
| --- | --- |
| Консалтинг | от 5000 ₽ |
| Enterprise | Цена по запросу |
""".strip()
    )

    result = await MarkdownPriceAcquisitionAdapter().acquire(
        project_id="project-1",
        price_document_id="price-doc-1",
        source_format=PriceDocumentSourceFormat.MARKDOWN,
        input_kind=PriceDocumentInputKind.MIXED,
        units=(unit,),
    )

    kinds = {
        candidate.item_name: candidate.value_kind
        for candidate in result.fact_candidates
    }

    assert kinds["Консалтинг"] == PriceValueKind.STARTING_FROM
    assert kinds["Enterprise"] == PriceValueKind.ON_REQUEST
    assert result.fact_candidates[1].price_text == "Цена по запросу"


@pytest.mark.asyncio
async def test_adapter_reports_issue_when_no_markdown_table_detected() -> None:
    result = await MarkdownPriceAcquisitionAdapter().acquire(
        project_id="project-1",
        price_document_id="price-doc-1",
        source_format=PriceDocumentSourceFormat.MARKDOWN,
        input_kind=PriceDocumentInputKind.STRUCTURED_TEXT,
        units=(_unit("Тариф Pro стоит 2490 ₽/мес."),),
    )

    assert result.fact_candidates == ()
    assert result.issues[0].code == PriceCompilationIssueCode.NEEDS_HUMAN_REVIEW


@pytest.mark.asyncio
async def test_adapter_reports_missing_price_column_without_crashing() -> None:
    unit = _unit(
        """
| Тариф | Описание |
| --- | --- |
| Pro | CRM для менеджеров |
""".strip()
    )

    result = await MarkdownPriceAcquisitionAdapter().acquire(
        project_id="project-1",
        price_document_id="price-doc-1",
        source_format=PriceDocumentSourceFormat.MARKDOWN,
        input_kind=PriceDocumentInputKind.MIXED,
        units=(unit,),
    )

    assert result.fact_candidates == ()
    assert any(
        issue.code == PriceCompilationIssueCode.MISSING_PRICE_VALUE
        for issue in result.issues
    )
