from __future__ import annotations

import pytest

from src.interfaces.composition.commercial_price_acquisition import (
    make_commercial_price_acquisition_service,
)
from src.domain.commercial.price_acquisition import PriceAcquisitionUnit
from src.domain.commercial.price_knowledge import (
    PriceDocumentInputKind,
    PriceDocumentSourceFormat,
    PriceValueKind,
)


@pytest.mark.asyncio
async def test_composition_builds_acquisition_service_with_markdown_adapter() -> None:
    service = make_commercial_price_acquisition_service()
    unit = PriceAcquisitionUnit(
        id="unit-1",
        price_document_id="price-doc-1",
        source_index=0,
        source_format=PriceDocumentSourceFormat.MARKDOWN,
        input_kind=PriceDocumentInputKind.MIXED,
        raw_text=("| Тариф | Цена |\n| --- | --- |\n| Pro | 2490 ₽ |"),
    )

    result = await service.acquire(
        project_id="project-1",
        price_document_id="price-doc-1",
        source_format=PriceDocumentSourceFormat.MARKDOWN,
        input_kind=PriceDocumentInputKind.MIXED,
        units=(unit,),
    )

    assert result.fact_candidates
    assert result.fact_candidates[0].project_id == "project-1"
    assert result.fact_candidates[0].item_name == "Pro"
    assert result.fact_candidates[0].value_kind == PriceValueKind.EXACT
