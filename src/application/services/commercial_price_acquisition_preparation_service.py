from __future__ import annotations

from collections.abc import Sequence

from src.application.ports.commercial_price_acquisition import (
    CommercialPriceAcquisitionServicePort,
)
from src.domain.commercial.price_acquisition import (
    PriceAcquisitionResult,
    PriceAcquisitionUnit,
    PriceCompilationIssue,
    PriceCompilationIssueCode,
    PriceCompilationIssueSeverity,
)
from src.domain.commercial.price_knowledge import (
    PriceDocument,
    PriceSourceUnit,
)


class CommercialPriceAcquisitionPreparationService:
    """Bridges persisted price source material into acquisition adapters.

    CommercialPriceIngestionService persists PriceSourceUnit records.
    Acquisition adapters consume PriceAcquisitionUnit records. This service
    keeps that conversion explicit so CSV, XLSX, Markdown, PDF, structured
    text, and unstructured text adapters can share one input contract.
    """

    async def acquire_from_source_units(
        self,
        *,
        price_document: PriceDocument,
        source_units: Sequence[PriceSourceUnit],
        acquisition_service: CommercialPriceAcquisitionServicePort,
    ) -> PriceAcquisitionResult:
        acquisition_units = price_acquisition_units_from_source_units(
            price_document=price_document,
            source_units=source_units,
        )

        if not acquisition_units:
            return PriceAcquisitionResult(
                price_document_id=price_document.id,
                source_format=price_document.source_format,
                input_kind=price_document.input_kind,
                issues=(
                    PriceCompilationIssue(
                        severity=PriceCompilationIssueSeverity.ERROR,
                        code=PriceCompilationIssueCode.EMPTY_SOURCE_UNIT,
                        message=(
                            "Commercial price acquisition cannot start because "
                            "no source units are available."
                        ),
                    ),
                ),
            )

        return await acquisition_service.acquire(
            project_id=price_document.project_id,
            price_document_id=price_document.id,
            source_format=price_document.source_format,
            input_kind=price_document.input_kind,
            units=acquisition_units,
        )


def price_acquisition_unit_from_source_unit(
    *,
    price_document: PriceDocument,
    source_unit: PriceSourceUnit,
) -> PriceAcquisitionUnit:
    if source_unit.price_document_id != price_document.id:
        raise ValueError("price source unit document mismatch")

    return PriceAcquisitionUnit(
        id=source_unit.id,
        price_document_id=source_unit.price_document_id,
        source_index=source_unit.source_index,
        source_format=price_document.source_format,
        input_kind=source_unit.kind,
        raw_text=source_unit.raw_text,
        title=source_unit.title,
        metadata={
            **dict(source_unit.metadata),
            "knowledge_document_id": price_document.knowledge_document_id,
            "price_document_input_kind": price_document.input_kind.value,
            "price_document_source_format": price_document.source_format.value,
        },
    )


def price_acquisition_units_from_source_units(
    *,
    price_document: PriceDocument,
    source_units: Sequence[PriceSourceUnit],
) -> tuple[PriceAcquisitionUnit, ...]:
    return tuple(
        price_acquisition_unit_from_source_unit(
            price_document=price_document,
            source_unit=source_unit,
        )
        for source_unit in source_units
    )
