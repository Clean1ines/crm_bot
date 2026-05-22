from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import PurePath

from src.application.ports.commercial_price import CommercialPriceKnowledgePort
from src.domain.commercial.price_knowledge import (
    PriceDocument,
    PriceDocumentInputKind,
    PriceDocumentSourceFormat,
    PriceDocumentStatus,
    PriceSourceUnit,
)
from src.domain.project_plane.json_types import JsonObject


_PRICE_DOCUMENT_NAMESPACE = uuid.UUID("2a7c76e8-83da-42d8-ae8e-7a75fbe6f12a")
_PRICE_SOURCE_UNIT_NAMESPACE = uuid.UUID("9bda1f47-7d4c-44a9-a425-127a77415e17")


@dataclass(frozen=True, slots=True)
class CommercialPriceSourceIngestionResult:
    price_document_id: str
    source_unit_count: int
    status: PriceDocumentStatus


class CommercialPriceIngestionService:
    """Persists the source-material side of commercial price knowledge.

    This service intentionally does not extract concrete price facts yet.
    Its first responsibility is to give price_list uploads a durable,
    source-grounded commercial_price_* trace that can later be compiled into
    PriceFacts and used by runtime price lookup.
    """

    async def persist_price_source_material(
        self,
        *,
        project_id: str,
        knowledge_document_id: str,
        file_name: str,
        chunks: Sequence[JsonObject],
        price_repo: CommercialPriceKnowledgePort,
    ) -> CommercialPriceSourceIngestionResult:
        price_document_id = price_document_id_for_knowledge_document(
            project_id=project_id,
            knowledge_document_id=knowledge_document_id,
        )
        source_format = price_document_source_format(file_name)
        input_kind = price_document_input_kind(
            source_format=source_format,
            chunks=chunks,
        )

        await price_repo.create_price_document(
            PriceDocument(
                id=price_document_id,
                project_id=project_id,
                knowledge_document_id=knowledge_document_id,
                source_format=source_format,
                input_kind=input_kind,
                status=PriceDocumentStatus.PROCESSING,
            )
        )

        source_units = price_source_units_from_chunks(
            price_document_id=price_document_id,
            file_name=file_name,
            input_kind=input_kind,
            chunks=chunks,
        )

        if not source_units:
            await price_repo.update_price_document_status(
                project_id=project_id,
                price_document_id=price_document_id,
                status=PriceDocumentStatus.FAILED,
                error="No indexable price source units extracted",
            )
            return CommercialPriceSourceIngestionResult(
                price_document_id=price_document_id,
                source_unit_count=0,
                status=PriceDocumentStatus.FAILED,
            )

        await price_repo.replace_price_source_units(
            project_id=project_id,
            price_document_id=price_document_id,
            units=source_units,
        )
        await price_repo.update_price_document_status(
            project_id=project_id,
            price_document_id=price_document_id,
            status=PriceDocumentStatus.READY,
        )

        return CommercialPriceSourceIngestionResult(
            price_document_id=price_document_id,
            source_unit_count=len(source_units),
            status=PriceDocumentStatus.READY,
        )


def price_document_id_for_knowledge_document(
    *,
    project_id: str,
    knowledge_document_id: str,
) -> str:
    return str(
        uuid.uuid5(
            _PRICE_DOCUMENT_NAMESPACE,
            f"{project_id}:{knowledge_document_id}",
        )
    )


def price_source_unit_id(
    *,
    price_document_id: str,
    source_index: int,
) -> str:
    return str(
        uuid.uuid5(
            _PRICE_SOURCE_UNIT_NAMESPACE,
            f"{price_document_id}:{source_index}",
        )
    )


def price_document_source_format(file_name: str) -> PriceDocumentSourceFormat:
    suffix = PurePath(file_name or "").suffix.lower()

    if suffix in {".md", ".markdown"}:
        return PriceDocumentSourceFormat.MARKDOWN
    if suffix in {".txt", ".text"}:
        return PriceDocumentSourceFormat.PLAIN_TEXT
    if suffix == ".csv":
        return PriceDocumentSourceFormat.CSV
    if suffix in {".xlsx", ".xls"}:
        return PriceDocumentSourceFormat.XLSX
    if suffix == ".pdf":
        return PriceDocumentSourceFormat.PDF_TEXT

    return PriceDocumentSourceFormat.UNKNOWN


def price_document_input_kind(
    *,
    source_format: PriceDocumentSourceFormat,
    chunks: Sequence[JsonObject],
) -> PriceDocumentInputKind:
    if source_format in {
        PriceDocumentSourceFormat.CSV,
        PriceDocumentSourceFormat.XLSX,
        PriceDocumentSourceFormat.PDF_TABLE,
    }:
        return PriceDocumentInputKind.TABLE

    if any(_looks_like_table_chunk(chunk) for chunk in chunks):
        return PriceDocumentInputKind.MIXED

    if source_format in {
        PriceDocumentSourceFormat.MARKDOWN,
        PriceDocumentSourceFormat.PLAIN_TEXT,
        PriceDocumentSourceFormat.PDF_TEXT,
    }:
        return PriceDocumentInputKind.STRUCTURED_TEXT

    return PriceDocumentInputKind.UNKNOWN


def price_source_units_from_chunks(
    *,
    price_document_id: str,
    file_name: str,
    input_kind: PriceDocumentInputKind,
    chunks: Sequence[JsonObject],
) -> tuple[PriceSourceUnit, ...]:
    units: list[PriceSourceUnit] = []

    for fallback_index, chunk in enumerate(chunks):
        raw_text = _chunk_text(chunk)
        if not raw_text:
            continue

        source_index = _chunk_source_index(chunk, fallback_index)
        units.append(
            PriceSourceUnit(
                id=price_source_unit_id(
                    price_document_id=price_document_id,
                    source_index=source_index,
                ),
                price_document_id=price_document_id,
                source_index=source_index,
                kind=_source_unit_kind(chunk=chunk, default_kind=input_kind),
                raw_text=raw_text,
                title=_chunk_title(chunk),
                metadata=_source_unit_metadata(
                    file_name=file_name,
                    chunk=chunk,
                    fallback_index=fallback_index,
                ),
            )
        )

    return tuple(units)


def _chunk_text(chunk: Mapping[str, object]) -> str:
    for key in (
        "content",
        "text",
        "raw_text",
        "source_text",
        "page_content",
        "markdown",
    ):
        value = chunk.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    return ""


def _chunk_source_index(chunk: Mapping[str, object], fallback_index: int) -> int:
    for key in ("source_index", "chunk_index", "index"):
        value = chunk.get(key)
        parsed = _optional_int(value)
        if parsed is not None and parsed >= 0:
            return parsed

    return fallback_index


def _chunk_title(chunk: Mapping[str, object]) -> str:
    for key in ("title", "section_title", "heading", "path"):
        value = chunk.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    return ""


def _source_unit_kind(
    *,
    chunk: Mapping[str, object],
    default_kind: PriceDocumentInputKind,
) -> PriceDocumentInputKind:
    if _looks_like_table_chunk(chunk):
        return PriceDocumentInputKind.TABLE

    if default_kind == PriceDocumentInputKind.MIXED:
        return PriceDocumentInputKind.STRUCTURED_TEXT

    return default_kind


def _source_unit_metadata(
    *,
    file_name: str,
    chunk: Mapping[str, object],
    fallback_index: int,
) -> dict[str, object]:
    metadata: dict[str, object] = {
        "file_name": file_name,
        "chunk_index": fallback_index,
    }

    for key in (
        "source_index",
        "chunk_index",
        "page",
        "start_offset",
        "end_offset",
        "section_title",
        "heading",
        "path",
    ):
        value = chunk.get(key)
        if _is_metadata_scalar(value):
            metadata[key] = value

    return metadata


def _looks_like_table_chunk(chunk: Mapping[str, object]) -> bool:
    table_like = chunk.get("table_like")
    if isinstance(table_like, bool):
        return table_like

    kind = chunk.get("kind")
    if isinstance(kind, str) and kind.lower() in {"table", "csv", "spreadsheet"}:
        return True

    content_type = chunk.get("content_type")
    if isinstance(content_type, str) and content_type.lower() in {
        "table",
        "csv",
        "spreadsheet",
    }:
        return True

    text = _chunk_text(chunk)
    if "|" in text and "\n" in text:
        return True
    if (
        "," in text
        and "\n" in text
        and any(marker in text.lower() for marker in ("price", "цена", "тариф"))
    ):
        return True

    return False


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())

    return None


def _is_metadata_scalar(value: object) -> bool:
    return isinstance(value, str | int | float | bool) or value is None
