from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from src.domain.commercial.price_acquisition import (
    PriceAcquisitionResult,
    PriceAcquisitionUnit,
)
from src.domain.commercial.price_knowledge import (
    PriceDocumentInputKind,
    PriceDocumentSourceFormat,
)


class CommercialPriceAcquisitionAdapterPort(Protocol):
    """Format-specific acquisition adapter.

    Adapters may target CSV, XLSX, Markdown tables, PDF tables, structured text,
    unstructured text, or mixed source documents. They must return the common
    domain acquisition result instead of leaking source-format details into
    runtime price lookup.
    """

    @property
    def adapter_name(self) -> str: ...

    def supports(
        self,
        *,
        source_format: PriceDocumentSourceFormat,
        input_kind: PriceDocumentInputKind,
    ) -> bool: ...

    async def acquire(
        self,
        *,
        project_id: str,
        price_document_id: str,
        source_format: PriceDocumentSourceFormat,
        input_kind: PriceDocumentInputKind,
        units: Sequence[PriceAcquisitionUnit],
    ) -> PriceAcquisitionResult: ...


class CommercialPriceAcquisitionServicePort(Protocol):
    async def acquire(
        self,
        *,
        project_id: str,
        price_document_id: str,
        source_format: PriceDocumentSourceFormat,
        input_kind: PriceDocumentInputKind,
        units: Sequence[PriceAcquisitionUnit],
    ) -> PriceAcquisitionResult: ...
