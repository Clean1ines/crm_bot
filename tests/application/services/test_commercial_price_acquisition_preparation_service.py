from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

import pytest

from src.application.services.commercial_price_acquisition_preparation_service import (
    CommercialPriceAcquisitionPreparationService,
    price_acquisition_unit_from_source_unit,
    price_acquisition_units_from_source_units,
)
from src.domain.commercial.price_acquisition import (
    PriceAcquisitionResult,
    PriceAcquisitionUnit,
    PriceCompilationIssueCode,
    PriceCompilationIssueSeverity,
)
from src.domain.commercial.price_knowledge import (
    PriceDocument,
    PriceDocumentInputKind,
    PriceDocumentSourceFormat,
    PriceDocumentStatus,
    PriceSourceUnit,
)


def _price_document() -> PriceDocument:
    return PriceDocument(
        id="price-doc-1",
        project_id="project-1",
        knowledge_document_id="knowledge-doc-1",
        source_format=PriceDocumentSourceFormat.CSV,
        input_kind=PriceDocumentInputKind.TABLE,
        status=PriceDocumentStatus.READY,
    )


def _source_unit() -> PriceSourceUnit:
    return PriceSourceUnit(
        id="unit-1",
        price_document_id="price-doc-1",
        source_index=0,
        kind=PriceDocumentInputKind.TABLE,
        raw_text="service,price\nPro,2490",
        title="main",
        metadata={"sheet": "main"},
    )


@dataclass
class FakeAcquisitionService:
    calls: list[tuple[str, str, PriceDocumentSourceFormat, PriceDocumentInputKind]] = (
        field(default_factory=list)
    )
    units_seen: tuple[PriceAcquisitionUnit, ...] = ()

    async def acquire(
        self,
        *,
        project_id: str,
        price_document_id: str,
        source_format: PriceDocumentSourceFormat,
        input_kind: PriceDocumentInputKind,
        units: Sequence[PriceAcquisitionUnit],
    ) -> PriceAcquisitionResult:
        self.calls.append((project_id, price_document_id, source_format, input_kind))
        self.units_seen = tuple(units)
        return PriceAcquisitionResult(
            price_document_id=price_document_id,
            source_format=source_format,
            input_kind=input_kind,
            units=tuple(units),
        )


def test_price_acquisition_unit_from_source_unit_preserves_source_material() -> None:
    unit = price_acquisition_unit_from_source_unit(
        price_document=_price_document(),
        source_unit=_source_unit(),
    )

    assert unit == PriceAcquisitionUnit(
        id="unit-1",
        price_document_id="price-doc-1",
        source_index=0,
        source_format=PriceDocumentSourceFormat.CSV,
        input_kind=PriceDocumentInputKind.TABLE,
        raw_text="service,price\nPro,2490",
        title="main",
        metadata={
            "sheet": "main",
            "knowledge_document_id": "knowledge-doc-1",
            "price_document_input_kind": "table",
            "price_document_source_format": "csv",
        },
    )


def test_price_acquisition_unit_from_source_unit_rejects_document_mismatch() -> None:
    with pytest.raises(ValueError, match="document mismatch"):
        price_acquisition_unit_from_source_unit(
            price_document=_price_document(),
            source_unit=PriceSourceUnit(
                id="unit-2",
                price_document_id="other-price-doc",
                source_index=0,
                kind=PriceDocumentInputKind.TABLE,
                raw_text="service,price\nPro,2490",
            ),
        )


def test_price_acquisition_units_from_source_units_preserves_order() -> None:
    first = _source_unit()
    second = PriceSourceUnit(
        id="unit-2",
        price_document_id="price-doc-1",
        source_index=1,
        kind=PriceDocumentInputKind.TABLE,
        raw_text="service,price\nBasic,990",
    )

    units = price_acquisition_units_from_source_units(
        price_document=_price_document(),
        source_units=(first, second),
    )

    assert tuple(unit.id for unit in units) == ("unit-1", "unit-2")
    assert tuple(unit.source_index for unit in units) == (0, 1)


@pytest.mark.asyncio
async def test_preparation_service_delegates_to_acquisition_service() -> None:
    acquisition_service = FakeAcquisitionService()

    result = (
        await CommercialPriceAcquisitionPreparationService().acquire_from_source_units(
            price_document=_price_document(),
            source_units=(_source_unit(),),
            acquisition_service=acquisition_service,
        )
    )

    assert result.units == acquisition_service.units_seen
    assert acquisition_service.calls == [
        (
            "project-1",
            "price-doc-1",
            PriceDocumentSourceFormat.CSV,
            PriceDocumentInputKind.TABLE,
        )
    ]
    assert result.price_document_id == "price-doc-1"


@pytest.mark.asyncio
async def test_preparation_service_returns_error_issue_when_no_source_units() -> None:
    acquisition_service = FakeAcquisitionService()

    result = (
        await CommercialPriceAcquisitionPreparationService().acquire_from_source_units(
            price_document=_price_document(),
            source_units=(),
            acquisition_service=acquisition_service,
        )
    )

    assert acquisition_service.calls == []
    assert result.has_errors is True
    assert result.issues[0].severity == PriceCompilationIssueSeverity.ERROR
    assert result.issues[0].code == PriceCompilationIssueCode.EMPTY_SOURCE_UNIT
