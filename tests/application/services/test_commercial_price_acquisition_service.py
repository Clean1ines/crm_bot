from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import pytest

from src.application.services.commercial_price_acquisition_service import (
    CommercialPriceAcquisitionService,
)
from src.domain.commercial.price_acquisition import (
    PriceAcquisitionResult,
    PriceAcquisitionUnit,
    PriceCompilationIssueCode,
    PriceCompilationIssueSeverity,
)
from src.domain.commercial.price_knowledge import (
    PriceDocumentInputKind,
    PriceDocumentSourceFormat,
)


def _unit() -> PriceAcquisitionUnit:
    return PriceAcquisitionUnit(
        id="unit-1",
        price_document_id="price-doc-1",
        source_index=0,
        source_format=PriceDocumentSourceFormat.CSV,
        input_kind=PriceDocumentInputKind.TABLE,
        raw_text="service,price\nPro,2490",
    )


@dataclass(frozen=True)
class FakeAcquisitionAdapter:
    name: str
    supported_format: PriceDocumentSourceFormat
    supported_kind: PriceDocumentInputKind
    should_fail: bool = False

    @property
    def adapter_name(self) -> str:
        return self.name

    def supports(
        self,
        *,
        source_format: PriceDocumentSourceFormat,
        input_kind: PriceDocumentInputKind,
    ) -> bool:
        return (
            source_format == self.supported_format and input_kind == self.supported_kind
        )

    async def acquire(
        self,
        *,
        price_document_id: str,
        source_format: PriceDocumentSourceFormat,
        input_kind: PriceDocumentInputKind,
        units: Sequence[PriceAcquisitionUnit],
    ) -> PriceAcquisitionResult:
        if self.should_fail:
            raise RuntimeError("adapter exploded")

        return PriceAcquisitionResult(
            price_document_id=price_document_id,
            source_format=source_format,
            input_kind=input_kind,
            units=tuple(units),
        )


@pytest.mark.asyncio
async def test_service_selects_first_supporting_adapter() -> None:
    unsupported = FakeAcquisitionAdapter(
        name="markdown",
        supported_format=PriceDocumentSourceFormat.MARKDOWN,
        supported_kind=PriceDocumentInputKind.MIXED,
    )
    supported = FakeAcquisitionAdapter(
        name="csv",
        supported_format=PriceDocumentSourceFormat.CSV,
        supported_kind=PriceDocumentInputKind.TABLE,
    )

    result = await CommercialPriceAcquisitionService(
        adapters=(unsupported, supported),
    ).acquire(
        price_document_id="price-doc-1",
        source_format=PriceDocumentSourceFormat.CSV,
        input_kind=PriceDocumentInputKind.TABLE,
        units=(_unit(),),
    )

    assert result.price_document_id == "price-doc-1"
    assert result.source_format == PriceDocumentSourceFormat.CSV
    assert result.input_kind == PriceDocumentInputKind.TABLE
    assert result.units == (_unit(),)
    assert result.issues == ()


@pytest.mark.asyncio
async def test_service_returns_review_issue_when_no_adapter_supports_format() -> None:
    result = await CommercialPriceAcquisitionService(adapters=()).acquire(
        price_document_id="price-doc-1",
        source_format=PriceDocumentSourceFormat.UNKNOWN,
        input_kind=PriceDocumentInputKind.UNKNOWN,
        units=(_unit(),),
    )

    assert result.units == (_unit(),)
    assert result.needs_review is True
    assert result.issues[0].severity == PriceCompilationIssueSeverity.WARNING
    assert result.issues[0].code == PriceCompilationIssueCode.UNKNOWN_SOURCE_FORMAT
    assert result.issues[0].metadata["source_format"] == "unknown"


@pytest.mark.asyncio
async def test_service_converts_adapter_failure_to_error_issue() -> None:
    failing = FakeAcquisitionAdapter(
        name="csv",
        supported_format=PriceDocumentSourceFormat.CSV,
        supported_kind=PriceDocumentInputKind.TABLE,
        should_fail=True,
    )

    result = await CommercialPriceAcquisitionService(adapters=(failing,)).acquire(
        price_document_id="price-doc-1",
        source_format=PriceDocumentSourceFormat.CSV,
        input_kind=PriceDocumentInputKind.TABLE,
        units=(_unit(),),
    )

    assert result.has_errors is True
    assert result.issues[0].severity == PriceCompilationIssueSeverity.ERROR
    assert result.issues[0].code == PriceCompilationIssueCode.NEEDS_HUMAN_REVIEW
    assert result.issues[0].metadata["adapter_name"] == "csv"
