from __future__ import annotations

from dataclasses import dataclass, field
from typing import cast

import pytest

from src.application.ports.commercial_price import CommercialPriceKnowledgePort
from src.application.ports.commercial_price_acquisition import (
    CommercialPriceAcquisitionServicePort,
)
from src.application.services.commercial_price_acquisition_service import (
    CommercialPriceAcquisitionService,
)
from src.infrastructure.commercial_price.markdown_acquisition_adapter import (
    MarkdownPriceAcquisitionAdapter,
)

from src.application.services.commercial_price_ingestion_service import (
    CommercialPriceIngestionService,
    price_document_id_for_knowledge_document,
    price_document_input_kind,
    price_document_source_format,
    price_source_units_from_chunks,
)
from src.domain.commercial.price_knowledge import (
    PriceDocument,
    PriceDocumentInputKind,
    PriceDocumentSourceFormat,
    PriceDocumentStatus,
    PriceSourceUnit,
)


@dataclass
class FakeCommercialPriceRepo:
    documents: list[PriceDocument] = field(default_factory=list)
    source_units: list[PriceSourceUnit] = field(default_factory=list)
    statuses: list[tuple[str, PriceDocumentStatus, str | None]] = field(
        default_factory=list
    )

    async def create_price_document(self, document: PriceDocument) -> None:
        self.documents.append(document)

    async def replace_price_source_units(
        self,
        *,
        project_id: str,
        price_document_id: str,
        units: list[PriceSourceUnit] | tuple[PriceSourceUnit, ...],
    ) -> int:
        self.source_units = list(units)
        return len(units)

    async def update_price_document_status(
        self,
        *,
        project_id: str,
        price_document_id: str,
        status: PriceDocumentStatus,
        error: str | None = None,
    ) -> None:
        self.statuses.append((price_document_id, status, error))


def test_price_document_source_format_detects_common_price_file_types() -> None:
    assert price_document_source_format("price.csv") == PriceDocumentSourceFormat.CSV
    assert price_document_source_format("price.xlsx") == PriceDocumentSourceFormat.XLSX
    assert (
        price_document_source_format("price.md") == PriceDocumentSourceFormat.MARKDOWN
    )
    assert (
        price_document_source_format("price.pdf") == PriceDocumentSourceFormat.PDF_TEXT
    )
    assert (
        price_document_source_format("price.bin") == PriceDocumentSourceFormat.UNKNOWN
    )


def test_price_document_input_kind_prefers_table_formats() -> None:
    assert (
        price_document_input_kind(
            source_format=PriceDocumentSourceFormat.CSV,
            chunks=(),
        )
        == PriceDocumentInputKind.TABLE
    )
    assert (
        price_document_input_kind(
            source_format=PriceDocumentSourceFormat.MARKDOWN,
            chunks=({"content": "| service | price |\n| pro | 2490 |"},),
        )
        == PriceDocumentInputKind.MIXED
    )


def test_price_source_units_from_chunks_ignores_empty_chunks_and_preserves_metadata() -> (
    None
):
    price_document_id = price_document_id_for_knowledge_document(
        project_id="project-1",
        knowledge_document_id="document-1",
    )

    units = price_source_units_from_chunks(
        price_document_id=price_document_id,
        file_name="prices.md",
        input_kind=PriceDocumentInputKind.STRUCTURED_TEXT,
        chunks=(
            {"content": "  ", "source_index": 0},
            {
                "content": "## Pro\nЦена: 2490 ₽/мес.",
                "source_index": "3",
                "section_title": "Pro",
                "page": 2,
            },
        ),
    )

    assert len(units) == 1
    assert units[0].price_document_id == price_document_id
    assert units[0].source_index == 3
    assert units[0].kind == PriceDocumentInputKind.STRUCTURED_TEXT
    assert units[0].title == "Pro"
    assert units[0].raw_text == "## Pro\nЦена: 2490 ₽/мес."
    assert units[0].metadata["file_name"] == "prices.md"
    assert units[0].metadata["page"] == 2


@pytest.mark.asyncio
async def test_service_persists_price_document_and_source_units() -> None:
    repo = FakeCommercialPriceRepo()
    result = await CommercialPriceIngestionService().persist_price_source_material(
        project_id="project-1",
        knowledge_document_id="document-1",
        file_name="prices.csv",
        chunks=(
            {
                "content": "service,price\nPro,2490",
                "source_index": 0,
                "kind": "table",
            },
        ),
        price_repo=cast(CommercialPriceKnowledgePort, repo),
    )

    assert result.status == PriceDocumentStatus.READY
    assert result.source_unit_count == 1
    assert repo.documents == [
        PriceDocument(
            id=result.price_document_id,
            project_id="project-1",
            knowledge_document_id="document-1",
            source_format=PriceDocumentSourceFormat.CSV,
            input_kind=PriceDocumentInputKind.TABLE,
            status=PriceDocumentStatus.PROCESSING,
        )
    ]
    assert repo.source_units[0].kind == PriceDocumentInputKind.TABLE
    assert repo.statuses == [
        (result.price_document_id, PriceDocumentStatus.READY, None)
    ]


@pytest.mark.asyncio
async def test_service_marks_price_document_failed_when_no_source_units() -> None:
    repo = FakeCommercialPriceRepo()
    result = await CommercialPriceIngestionService().persist_price_source_material(
        project_id="project-1",
        knowledge_document_id="document-1",
        file_name="prices.txt",
        chunks=({"content": "   "},),
        price_repo=cast(CommercialPriceKnowledgePort, repo),
    )

    assert result.status == PriceDocumentStatus.FAILED
    assert result.source_unit_count == 0
    assert repo.source_units == []
    assert repo.statuses == [
        (
            result.price_document_id,
            PriceDocumentStatus.FAILED,
            "No indexable price source units extracted",
        )
    ]


@pytest.mark.asyncio
async def test_service_runs_optional_acquisition_for_price_source_material() -> None:
    repo = FakeCommercialPriceRepo()
    acquisition_service = CommercialPriceAcquisitionService(
        adapters=(MarkdownPriceAcquisitionAdapter(),)
    )

    result = await CommercialPriceIngestionService().persist_price_source_material(
        project_id="project-1",
        knowledge_document_id="document-1",
        file_name="prices.md",
        chunks=(
            {
                "content": "| Тариф | Цена |\n| --- | --- |\n| Pro | 2490 ₽ |",
                "source_index": 0,
                "kind": "table",
            },
        ),
        price_repo=cast(CommercialPriceKnowledgePort, repo),
        acquisition_service=cast(
            CommercialPriceAcquisitionServicePort,
            acquisition_service,
        ),
    )

    assert result.status == PriceDocumentStatus.READY
    assert result.acquisition_result is not None
    assert result.acquisition_row_count == 1
    assert result.acquisition_fact_candidate_count == 1
    assert result.acquisition_issue_count == 0
    assert result.acquisition_result.fact_candidates[0].project_id == "project-1"
