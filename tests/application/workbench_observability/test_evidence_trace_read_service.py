from __future__ import annotations
from datetime import datetime, timezone
from typing import Mapping, Sequence

import pytest

from src.application.workbench_observability.evidence_trace import (
    WorkbenchEvidenceTraceNotFoundError,
    WorkbenchEvidenceTraceReadService,
)


class FakeEvidenceTraceQuery:
    def __init__(
        self,
        *,
        document: Mapping[str, object] | None,
        sections: Sequence[Mapping[str, object]] = (),
        findings: Sequence[Mapping[str, object]] = (),
        canonical_facts: Sequence[Mapping[str, object]] = (),
        surfaces: Sequence[Mapping[str, object]] = (),
    ) -> None:
        self.document = document
        self.sections = sections
        self.findings = findings
        self.canonical_facts = canonical_facts
        self.surfaces = surfaces
        self.calls: list[str] = []

    async def get_evidence_trace_document(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> Mapping[str, object] | None:
        self.calls.append(f"document:{project_id}:{document_id}")
        return self.document

    async def list_evidence_trace_sections(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> Sequence[Mapping[str, object]]:
        self.calls.append(f"sections:{project_id}:{document_id}")
        return self.sections

    async def list_evidence_trace_findings(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> Sequence[Mapping[str, object]]:
        self.calls.append(f"findings:{project_id}:{document_id}")
        return self.findings

    async def list_evidence_trace_canonical_facts(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> Sequence[Mapping[str, object]]:
        self.calls.append(f"registry:{project_id}:{document_id}")
        return self.canonical_facts

    async def list_evidence_trace_surfaces(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> Sequence[Mapping[str, object]]:
        self.calls.append(f"surfaces:{project_id}:{document_id}")
        return self.surfaces


def _now() -> datetime:
    return datetime(2026, 5, 31, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_evidence_trace_groups_findings_canonical_facts_and_surfaces() -> None:
    query = FakeEvidenceTraceQuery(
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
        sections=[
            {
                "section_id": "section-1",
                "section_key": "s1",
                "section_index": 0,
                "title": "Delivery",
                "status": "processed",
                "raw_text": "Delivery takes two days. " * 80,
                "normalized_text": "Delivery takes two days.",
                "source_refs": ["document-1#s1"],
                "source_chunk_indexes": [0],
                "metadata": {"page": 1},
                "created_at": _now(),
                "updated_at": _now(),
            }
        ],
        findings=[
            {
                "finding_id": "finding-1",
                "section_id": "section-1",
                "action": "create",
                "target_fact_id": None,
                "target_surface_key": None,
                "local_surface_key": "delivery",
                "title": "Delivery",
                "canonical_question": "How long does delivery take?",
                "surface_kind": "faq",
                "answer": "Delivery takes two days.",
                "short_answer": "Two days.",
                "answer_delta": None,
                "variants": ["Delivery time?"],
                "evidence_quotes": ["Delivery takes two days."],
                "source_refs": ["document-1#s1"],
                "source_chunk_indexes": [0],
                "confidence": 0.9,
                "reason": "Explicit statement",
                "status": "accepted",
                "created_at": _now(),
            }
        ],
        canonical_facts=[
            {
                "fact_id": "registry-entry-1",
                "fact_key": "delivery",
                "canonical_question": "How long does delivery take?",
                "question_variants": ["Delivery time?"],
                "surface_kind": "faq",
                "answer": "Delivery takes two days.",
                "short_answer": "Two days.",
                "evidence_quotes": ["Delivery takes two days."],
                "source_refs": ["document-1#s1"],
                "source_section_ids": ["section-1"],
                "source_chunk_indexes": [0],
                "status": "active",
                "updated_at": _now(),
            }
        ],
        surfaces=[
            {
                "surface_id": "surface-1",
                "fact_id": "registry-entry-1",
                "title": "Delivery",
                "canonical_question": "How long does delivery take?",
                "question_variants": ["Delivery time?"],
                "answer": "Delivery takes two days.",
                "short_answer": "Two days.",
                "evidence_quotes": ["Delivery takes two days."],
                "source_refs": ["document-1#s1"],
                "source_section_ids": ["section-1"],
                "surface_kind": "faq",
                "status": "published",
                "curation_state": "ready",
                "created_at": _now(),
                "updated_at": _now(),
            }
        ],
    )

    payload = await WorkbenchEvidenceTraceReadService(
        query
    ).fetch_document_evidence_trace(
        project_id="project-1",
        document_id="document-1",
    )

    assert payload["document"]["document_id"] == "document-1"
    source_unit = payload["source_units"][0]
    assert source_unit["section_id"] == "section-1"
    assert len(source_unit["findings"]) == 1
    assert len(source_unit["canonical_facts"]) == 1
    assert len(source_unit["surfaces"]) == 1
    assert payload["coverage"] == {
        "source_units_total": 1,
        "source_units_with_source_refs": 1,
        "findings_total": 1,
        "findings_with_evidence": 1,
        "canonical_facts_total": 1,
        "canonical_facts_with_evidence": 1,
        "surfaces_total": 1,
        "surfaces_with_evidence": 1,
    }
    assert payload["gaps"]["ungrounded_surfaces"] == []


@pytest.mark.asyncio
async def test_evidence_trace_raises_for_missing_document() -> None:
    query = FakeEvidenceTraceQuery(document=None)

    with pytest.raises(WorkbenchEvidenceTraceNotFoundError):
        await WorkbenchEvidenceTraceReadService(query).fetch_document_evidence_trace(
            project_id="project-1",
            document_id="missing",
        )

    assert query.calls == ["document:project-1:missing"]


@pytest.mark.asyncio
async def test_evidence_trace_reports_ungrounded_surfaces() -> None:
    query = FakeEvidenceTraceQuery(
        document={
            "project_id": "project-1",
            "document_id": "document-1",
            "file_name": "faq.md",
            "source_type": "markdown",
            "file_size_bytes": 42,
            "status": "processed",
            "current_processing_run_id": None,
            "created_at": _now(),
            "updated_at": _now(),
            "deleted_at": None,
        },
        sections=[],
        surfaces=[
            {
                "surface_id": "surface-ungrounded",
                "fact_id": None,
                "title": "Ungrounded",
                "canonical_question": "Ungrounded?",
                "question_variants": [],
                "answer": "No evidence.",
                "short_answer": "No evidence.",
                "evidence_quotes": [],
                "source_refs": [],
                "source_section_ids": [],
                "surface_kind": "faq",
                "status": "draft",
                "curation_state": "needs_review",
                "created_at": _now(),
                "updated_at": _now(),
            }
        ],
    )

    payload = await WorkbenchEvidenceTraceReadService(
        query
    ).fetch_document_evidence_trace(
        project_id="project-1",
        document_id="document-1",
    )

    assert payload["coverage"]["surfaces_total"] == 1
    assert payload["coverage"]["surfaces_with_evidence"] == 0
    assert payload["gaps"]["ungrounded_surfaces"][0]["surface_id"] == (
        "surface-ungrounded"
    )
