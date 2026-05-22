from __future__ import annotations

from collections.abc import Sequence

from src.application.ports.commercial_price_acquisition import (
    CommercialPriceAcquisitionAdapterPort,
)
from src.domain.commercial.price_acquisition import (
    PriceAcquisitionResult,
    PriceAcquisitionUnit,
    PriceCompilationIssue,
    PriceCompilationIssueCode,
    PriceCompilationIssueSeverity,
)
from src.domain.commercial.price_knowledge import (
    PriceDocumentInputKind,
    PriceDocumentSourceFormat,
)


class CommercialPriceAcquisitionService:
    """Selects a format-specific price acquisition adapter.

    This service is intentionally format-neutral. CSV, XLSX, Markdown table,
    PDF table, structured text, and unstructured text adapters plug in through
    CommercialPriceAcquisitionAdapterPort and all return PriceAcquisitionResult.
    """

    def __init__(
        self,
        adapters: Sequence[CommercialPriceAcquisitionAdapterPort],
    ) -> None:
        self._adapters = tuple(adapters)

    async def acquire(
        self,
        *,
        price_document_id: str,
        source_format: PriceDocumentSourceFormat,
        input_kind: PriceDocumentInputKind,
        units: Sequence[PriceAcquisitionUnit],
    ) -> PriceAcquisitionResult:
        adapter = self._select_adapter(
            source_format=source_format,
            input_kind=input_kind,
        )
        if adapter is None:
            return PriceAcquisitionResult(
                price_document_id=price_document_id,
                source_format=source_format,
                input_kind=input_kind,
                units=tuple(units),
                issues=(
                    PriceCompilationIssue(
                        severity=PriceCompilationIssueSeverity.WARNING,
                        code=PriceCompilationIssueCode.UNKNOWN_SOURCE_FORMAT,
                        message=(
                            "No commercial price acquisition adapter supports "
                            f"{source_format.value}/{input_kind.value}."
                        ),
                        metadata={
                            "source_format": source_format.value,
                            "input_kind": input_kind.value,
                        },
                    ),
                ),
            )

        try:
            return await adapter.acquire(
                price_document_id=price_document_id,
                source_format=source_format,
                input_kind=input_kind,
                units=units,
            )
        except Exception as exc:
            return PriceAcquisitionResult(
                price_document_id=price_document_id,
                source_format=source_format,
                input_kind=input_kind,
                units=tuple(units),
                issues=(
                    PriceCompilationIssue(
                        severity=PriceCompilationIssueSeverity.ERROR,
                        code=PriceCompilationIssueCode.NEEDS_HUMAN_REVIEW,
                        message=(
                            "Commercial price acquisition adapter failed: "
                            f"{type(exc).__name__}"
                        ),
                        metadata={
                            "adapter_name": adapter.adapter_name,
                            "error": str(exc)[:500],
                        },
                    ),
                ),
            )

    def _select_adapter(
        self,
        *,
        source_format: PriceDocumentSourceFormat,
        input_kind: PriceDocumentInputKind,
    ) -> CommercialPriceAcquisitionAdapterPort | None:
        for adapter in self._adapters:
            if adapter.supports(source_format=source_format, input_kind=input_kind):
                return adapter

        return None
