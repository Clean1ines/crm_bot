from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from src.domain.commercial.price_knowledge import (
    PriceDocument,
    PriceDocumentStatus,
    PriceLookupQuery,
    PriceSourceRow,
    PriceSourceUnit,
    PublishedPriceFact,
)


class CommercialPriceDocumentPort(Protocol):
    async def create_price_document(self, document: PriceDocument) -> None: ...

    async def get_price_document_by_knowledge_document(
        self,
        *,
        project_id: str,
        knowledge_document_id: str,
    ) -> PriceDocument | None: ...

    async def get_price_document(
        self,
        *,
        project_id: str,
        price_document_id: str,
    ) -> PriceDocument | None: ...

    async def list_price_documents_for_project(
        self,
        *,
        project_id: str,
    ) -> tuple[PriceDocument, ...]: ...

    async def update_price_document_status(
        self,
        *,
        project_id: str,
        price_document_id: str,
        status: PriceDocumentStatus,
        error: str | None = None,
    ) -> None: ...


class CommercialPriceSourceMaterialPort(Protocol):
    async def replace_price_source_units(
        self,
        *,
        project_id: str,
        price_document_id: str,
        units: Sequence[PriceSourceUnit],
    ) -> int: ...

    async def list_price_source_units(
        self,
        *,
        project_id: str,
        price_document_id: str,
    ) -> tuple[PriceSourceUnit, ...]: ...

    async def replace_price_source_rows(
        self,
        *,
        project_id: str,
        price_document_id: str,
        source_unit_id: str,
        rows: Sequence[PriceSourceRow],
    ) -> int: ...

    async def list_price_source_rows(
        self,
        *,
        project_id: str,
        price_document_id: str,
        source_unit_id: str | None = None,
    ) -> tuple[PriceSourceRow, ...]: ...


class CommercialPriceFactPort(Protocol):
    async def replace_price_facts_for_document(
        self,
        *,
        project_id: str,
        price_document_id: str,
        facts: Sequence[PublishedPriceFact],
    ) -> int: ...

    async def list_price_facts_for_document(
        self,
        *,
        project_id: str,
        price_document_id: str,
        include_non_runtime: bool = False,
    ) -> tuple[PublishedPriceFact, ...]: ...

    async def list_price_facts_for_documents(
        self,
        *,
        project_id: str,
        price_document_ids: Sequence[str],
        include_non_runtime: bool = False,
    ) -> tuple[PublishedPriceFact, ...]: ...

    async def publish_price_facts(
        self,
        *,
        project_id: str,
        price_document_id: str,
        fact_ids: Sequence[str],
    ) -> int: ...

    async def reject_price_facts(
        self,
        *,
        project_id: str,
        price_document_id: str,
        fact_ids: Sequence[str],
        reason: str,
    ) -> int: ...


class CommercialPriceLookupPort(Protocol):
    async def list_published_price_facts_for_lookup(
        self,
        *,
        query: PriceLookupQuery,
        limit: int = 20,
    ) -> tuple[PublishedPriceFact, ...]: ...

    async def list_required_variant_slots(
        self,
        *,
        project_id: str,
        item_name: str,
    ) -> tuple[str, ...]: ...

    async def list_price_item_names(
        self,
        *,
        project_id: str,
        query_text: str | None = None,
        limit: int = 50,
    ) -> tuple[str, ...]: ...


class CommercialPriceKnowledgePort(
    CommercialPriceDocumentPort,
    CommercialPriceSourceMaterialPort,
    CommercialPriceFactPort,
    CommercialPriceLookupPort,
    Protocol,
):
    """Repository subset required by commercial price knowledge workflows."""
