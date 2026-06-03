from __future__ import annotations

from datetime import datetime, timezone
from typing import Mapping, Sequence

import pytest

from src.application.workbench_observability.surface_cards import (
    WorkbenchSurfaceCardsNotFoundError,
    WorkbenchSurfaceCardsReadService,
)


class FakeSurfaceCardsQuery:
    def __init__(
        self,
        *,
        document: Mapping[str, object] | None,
        cards: Sequence[Mapping[str, object]] = (),
    ) -> None:
        self.document = document
        self.cards = cards
        self.calls: list[str] = []

    async def get_surface_cards_document(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> Mapping[str, object] | None:
        self.calls.append(f"document:{project_id}:{document_id}")
        return self.document

    async def list_workbench_surface_cards(
        self,
        *,
        project_id: str,
        document_id: str,
        limit: int,
        offset: int,
    ) -> Sequence[Mapping[str, object]]:
        self.calls.append(f"cards:{project_id}:{document_id}:{limit}:{offset}")
        return self.cards


def _now() -> datetime:
    return datetime(2026, 5, 31, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_surface_cards_preserve_fragments_shape_and_add_workbench_metadata() -> (
    None
):
    query = FakeSurfaceCardsQuery(
        document={
            "project_id": "project-1",
            "document_id": "document-1",
            "file_name": "faq.md",
            "source_type": "markdown",
            "file_size_bytes": 42,
            "status": "processed",
            "current_processing_run_id": "processing-run-1",
            "created_at": _now(),
            "updated_at": _now(),
            "deleted_at": None,
        },
        cards=[
            {
                "surface_id": "surface-1",
                "project_id": "project-1",
                "document_id": "document-1",
                "processing_run_id": "processing-run-1",
                "registry_entry_id": "entry-1",
                "processing_method": "faq_section_registry_v1",
                "title": "Delivery",
                "canonical_question": "How long does delivery take?",
                "question_variants": ["Delivery time?"],
                "answer": "Delivery takes two days.",
                "short_answer": "Two days.",
                "answer_scope": "delivery",
                "question_scope": "delivery",
                "exclusion_scope": "",
                "evidence_quotes": ["Delivery takes two days."],
                "source_refs": ["document-1#s1"],
                "source_section_ids": ["section-1"],
                "surface_kind": "faq",
                "status": "ready",
                "curation_state": "ready",
                "created_at": _now(),
                "updated_at": _now(),
            },
            {
                "surface_id": "surface-2",
                "project_id": "project-1",
                "document_id": "document-1",
                "processing_run_id": "processing-run-1",
                "registry_entry_id": "entry-2",
                "processing_method": "faq_section_registry_v1",
                "title": "Payment",
                "canonical_question": "How can I pay?",
                "question_variants": [],
                "answer": "Card only.",
                "short_answer": "Card only.",
                "answer_scope": "payment",
                "question_scope": "payment",
                "exclusion_scope": "",
                "evidence_quotes": [],
                "source_refs": [],
                "source_section_ids": [],
                "surface_kind": "faq",
                "status": "draft",
                "curation_state": "needs_review",
                "created_at": _now(),
                "updated_at": _now(),
            },
        ],
    )

    payload = await WorkbenchSurfaceCardsReadService(
        query
    ).fetch_document_surface_cards(
        project_id="project-1",
        document_id="document-1",
        limit=100,
        offset=0,
    )

    assert payload["document"]["document_id"] == "document-1"
    assert payload["items"] is payload["fragments"]
    assert payload["surface_cards"] is payload["fragments"]
    assert payload["counts"] == {
        "total": 2,
        "by_status": {"draft": 1, "ready": 1},
        "by_curation_state": {"needs_review": 1, "ready": 1},
    }

    first = payload["fragments"][0]
    assert first["fragment_id"] == "surface-1"
    assert first["surface_id"] == "surface-1"
    assert first["canonical_question"] == "How long does delivery take?"
    assert first["source_refs"] == ["document-1#s1"]
    assert first["source_section_ids"] == ["section-1"]
    assert query.calls == [
        "document:project-1:document-1",
        "cards:project-1:document-1:100:0",
    ]


@pytest.mark.asyncio
async def test_surface_cards_raises_for_missing_document() -> None:
    query = FakeSurfaceCardsQuery(document=None)

    with pytest.raises(WorkbenchSurfaceCardsNotFoundError):
        await WorkbenchSurfaceCardsReadService(query).fetch_document_surface_cards(
            project_id="project-1",
            document_id="missing",
            limit=100,
            offset=0,
        )

    assert query.calls == ["document:project-1:missing"]


@pytest.mark.asyncio
async def test_surface_cards_allows_empty_cards() -> None:
    query = FakeSurfaceCardsQuery(
        document={
            "project_id": "project-1",
            "document_id": "document-1",
            "file_name": "faq.md",
            "source_type": "markdown",
            "file_size_bytes": 42,
            "status": "sectioned",
            "current_processing_run_id": None,
            "created_at": _now(),
            "updated_at": _now(),
            "deleted_at": None,
        },
        cards=[],
    )

    payload = await WorkbenchSurfaceCardsReadService(
        query
    ).fetch_document_surface_cards(
        project_id="project-1",
        document_id="document-1",
        limit=100,
        offset=0,
    )

    assert payload["fragments"] == []
    assert payload["counts"] == {
        "total": 0,
        "by_status": {},
        "by_curation_state": {},
    }
