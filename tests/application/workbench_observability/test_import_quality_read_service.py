from __future__ import annotations

from datetime import datetime, timezone
from typing import Mapping, Sequence

import pytest

from src.application.workbench_observability.import_quality import (
    WorkbenchImportQualityNotFoundError,
    WorkbenchImportQualityReadService,
)


class FakeImportQualityQuery:
    def __init__(
        self,
        *,
        document: Mapping[str, object] | None,
        sections: Sequence[Mapping[str, object]] = (),
        findings: Sequence[Mapping[str, object]] = (),
        canonical_facts: Sequence[Mapping[str, object]] = (),
        surfaces: Sequence[Mapping[str, object]] = (),
        node_runs: Sequence[Mapping[str, object]] = (),
    ) -> None:
        self.document = document
        self.sections = sections
        self.findings = findings
        self.canonical_facts = canonical_facts
        self.surfaces = surfaces
        self.node_runs = node_runs
        self.calls: list[str] = []

    async def get_import_quality_document(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> Mapping[str, object] | None:
        self.calls.append(f"document:{project_id}:{document_id}")
        return self.document

    async def list_import_quality_sections(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> Sequence[Mapping[str, object]]:
        self.calls.append(f"sections:{project_id}:{document_id}")
        return self.sections

    async def list_import_quality_findings(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> Sequence[Mapping[str, object]]:
        self.calls.append(f"findings:{project_id}:{document_id}")
        return self.findings

    async def list_import_quality_canonical_facts(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> Sequence[Mapping[str, object]]:
        self.calls.append(f"registry:{project_id}:{document_id}")
        return self.canonical_facts

    async def list_import_quality_surfaces(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> Sequence[Mapping[str, object]]:
        self.calls.append(f"surfaces:{project_id}:{document_id}")
        return self.surfaces

    async def list_import_quality_node_runs(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> Sequence[Mapping[str, object]]:
        self.calls.append(f"node_runs:{project_id}:{document_id}")
        return self.node_runs


def _now() -> datetime:
    return datetime(2026, 5, 31, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_import_quality_report_marks_ok_when_all_units_are_grounded() -> None:
    query = FakeImportQualityQuery(
        document={
            "project_id": "project-1",
            "document_id": "document-1",
            "file_name": "faq.md",
            "source_type": "markdown",
            "file_size_bytes": 42,
            "status": "processed",
            "current_processing_run_id": "run-1",
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
                "source_refs": ["document-1#s1"],
                "source_chunk_indexes": [0],
            }
        ],
        findings=[
            {
                "finding_id": "finding-1",
                "section_id": "section-1",
                "action": "create",
                "status": "accepted",
                "evidence_quotes": ["Delivery takes two days."],
                "source_refs": ["document-1#s1"],
                "source_chunk_indexes": [0],
                "confidence": 0.9,
            }
        ],
        canonical_facts=[
            {
                "fact_id": "entry-1",
                "fact_key": "delivery",
                "status": "active",
                "evidence_quotes": ["Delivery takes two days."],
                "source_refs": ["document-1#s1"],
                "source_section_ids": ["section-1"],
                "source_chunk_indexes": [0],
            }
        ],
        surfaces=[
            {
                "surface_id": "surface-1",
                "fact_id": "entry-1",
                "status": "ready",
                "curation_state": "ready",
                "evidence_quotes": ["Delivery takes two days."],
                "source_refs": ["document-1#s1"],
                "source_section_ids": ["section-1"],
            }
        ],
        node_runs=[
            {
                "node_run_id": "node-1",
                "processing_run_id": "run-1",
                "node_name": "claim_observations",
                "status": "completed",
                "error_kind": None,
                "error_message": None,
                "started_at": _now(),
                "completed_at": _now(),
            }
        ],
    )

    report = await WorkbenchImportQualityReadService(query).fetch_import_quality_report(
        project_id="project-1",
        document_id="document-1",
    )

    assert report["status"] == "ok"
    assert report["summary"] == {
        "sections_total": 1,
        "findings_total": 1,
        "canonical_facts_total": 1,
        "surfaces_total": 1,
        "node_runs_total": 1,
        "warnings_total": 0,
    }
    assert report["section_quality"]["sections_without_findings_count"] == 0
    assert report["evidence_quality"]["surfaces_without_evidence_count"] == 0
    assert report["node_quality"]["failed_node_runs_count"] == 0
    assert report["warnings"] == []


@pytest.mark.asyncio
async def test_import_quality_report_flags_missing_evidence_and_failed_nodes() -> None:
    query = FakeImportQualityQuery(
        document={
            "project_id": "project-1",
            "document_id": "document-1",
            "file_name": "faq.md",
            "source_type": "markdown",
            "file_size_bytes": 42,
            "status": "processing",
            "current_processing_run_id": "run-1",
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
                "source_refs": [],
                "source_chunk_indexes": [],
            },
            {
                "section_id": "section-2",
                "section_key": "s2",
                "section_index": 1,
                "title": "Payment",
                "status": "processed",
                "source_refs": [],
                "source_chunk_indexes": [],
            },
        ],
        findings=[
            {
                "finding_id": "finding-1",
                "section_id": "section-1",
                "action": "create",
                "status": "accepted",
                "evidence_quotes": [],
                "source_refs": [],
                "source_chunk_indexes": [],
                "confidence": None,
            }
        ],
        canonical_facts=[
            {
                "fact_id": "entry-1",
                "fact_key": "delivery",
                "status": "active",
                "evidence_quotes": [],
                "source_refs": [],
                "source_section_ids": [],
                "source_chunk_indexes": [],
            }
        ],
        surfaces=[
            {
                "surface_id": "surface-1",
                "fact_id": "entry-1",
                "status": "draft",
                "curation_state": "needs_review",
                "evidence_quotes": [],
                "source_refs": [],
                "source_section_ids": ["missing-section"],
            }
        ],
        node_runs=[
            {
                "node_run_id": "node-1",
                "processing_run_id": "run-1",
                "node_name": "claim_observations",
                "status": "failed",
                "error_kind": "provider_error",
                "error_message": "LLM failed",
                "started_at": _now(),
                "completed_at": _now(),
            }
        ],
    )

    report = await WorkbenchImportQualityReadService(query).fetch_import_quality_report(
        project_id="project-1",
        document_id="document-1",
    )

    assert report["status"] == "failed"
    assert report["section_quality"]["sections_without_findings_count"] == 1
    assert report["evidence_quality"] == {
        "findings_without_evidence_count": 1,
        "canonical_facts_without_evidence_count": 1,
        "surfaces_without_evidence_count": 0,
        "surfaces_with_missing_sections_count": 1,
    }
    assert report["node_quality"]["failed_node_runs_count"] == 1
    assert [warning["code"] for warning in report["warnings"]] == [
        "sections_without_findings",
        "findings_without_evidence",
        "canonical_facts_without_evidence",
        "surfaces_with_missing_sections",
        "failed_node_runs",
    ]


@pytest.mark.asyncio
async def test_import_quality_report_raises_for_missing_document() -> None:
    query = FakeImportQualityQuery(document=None)

    with pytest.raises(WorkbenchImportQualityNotFoundError):
        await WorkbenchImportQualityReadService(query).fetch_import_quality_report(
            project_id="project-1",
            document_id="missing",
        )

    assert query.calls == ["document:project-1:missing"]
