from __future__ import annotations

from src.application.ports.commercial_price_acquisition import (
    CommercialPriceAcquisitionServicePort,
)
from src.application.services.commercial_price_acquisition_service import (
    CommercialPriceAcquisitionService,
)
from src.infrastructure.commercial_price.markdown_acquisition_adapter import (
    MarkdownPriceAcquisitionAdapter,
)


def make_commercial_price_acquisition_service() -> (
    CommercialPriceAcquisitionServicePort
):
    """Build the commercial price acquisition service with known adapters.

    This belongs to composition: application owns the service/port contract, while
    infrastructure provides concrete format-specific adapters.
    """

    return CommercialPriceAcquisitionService(
        adapters=(MarkdownPriceAcquisitionAdapter(),)
    )
