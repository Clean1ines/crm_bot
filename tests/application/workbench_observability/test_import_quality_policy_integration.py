from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping, Sequence

import pytest

from src.application.workbench_observability.import_quality import (
    WorkbenchImportQualityReadService,
)


@dataclass(slots=True)
class FakeImportQualityQuery:
    document: Mapping[str, object] | None
    sections: Sequence[Mapping[str, object]] = ()
    findings: Sequence[Mapping[str, object]] = ()
    canonical_facts: Sequence[Mapping[str, object]] = ()
    surfaces: Sequence[Mapping[str, object]] = ()
    node_runs: Sequence[Mapping[str, object]] = ()

    async def get_import_quality_document(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> Mapping[str, object] | None:
        return self.document

    async def list_import_quality_sections(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> Sequence[Mapping[str, object]]:
        return self.sections

    async def list_import_quality_findings(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> Sequence[Mapping[str, object]]:
        return self.findings

    async def list_import_quality_canonical_facts(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> Sequence[Mapping[str, object]]:
        return self.canonical_facts

    async def list_import_quality_surfaces(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> Sequence[Mapping[str, object]]:
        return self.surfaces

    async def list_import_quality_node_runs(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> Sequence[Mapping[str, object]]:
        return self.node_runs


def _document() -> dict[str, object]:
    return {
        "project_id": "project-1",
        "document_id": "document-1",
        "file_name": "faq.md",
        "source_type": "markdown",
        "file_size_bytes": 42,
        "status": "uploaded",
        "current_processing_run_id": "run-1",
        "created_at": None,
        "updated_at": None,
        "deleted_at": None,
    }


def _section(section_id: str = "section-1") -> dict[str, object]:
    return {
        "section_id": section_id,
        "section_index": 0,
        "title": "FAQ",
        "heading_path": ["FAQ"],
        "status": "processed",
        "source_refs": ["document-1#section-1"],
        "source_chunk_indexes": [0],
    }


def _finding_without_evidence() -> dict[str, object]:
    return {
        "finding_id": "finding-1",
        "section_id": "section-1",
        "action": "new",
        "status": "proposed",
        "canonical_question": "Что это?",
        "evidence_quotes": [],
        "source_refs": [],
    }


@pytest.mark.asyncio
async def test_import_quality_policy_rejects_document_without_sections() -> None:
    service = WorkbenchImportQualityReadService(
        FakeImportQualityQuery(document=_document())
    )

    report = await service.fetch_import_quality_report(
        project_id="project-1",
        document_id="document-1",
    )

    assert report["status"] == "empty"
    assert report["quality_decision"] == {
        "action": "reject",
        "can_process": False,
        "issues": [
            {
                "code": "no_sections",
                "severity": "error",
                "message": "Document has no Workbench sections.",
            }
        ],
    }


@pytest.mark.asyncio
async def test_import_quality_policy_allows_processing_with_warnings() -> None:
    service = WorkbenchImportQualityReadService(
        FakeImportQualityQuery(
            document=_document(),
            sections=(_section(),),
            findings=(_finding_without_evidence(),),
        )
    )

    report = await service.fetch_import_quality_report(
        project_id="project-1",
        document_id="document-1",
    )

    decision = report["quality_decision"]
    assert isinstance(decision, dict)
    assert decision["action"] == "process_with_warnings"
    assert decision["can_process"] is True
    assert decision["issues"] == [
        {
            "code": "findings_without_evidence",
            "severity": "warning",
            "message": "Some findings have no explicit evidence.",
        }
    ]


def test_import_quality_read_side_uses_domain_policy_without_legacy_builder() -> None:
    source = "src/application/workbench_observability/import_quality.py"
    from pathlib import Path

    text = Path(source).read_text(encoding="utf-8")

    assert "knowledge_workbench.import_quality_policy" in text
    assert "decide_import_quality_action" in text
    assert "knowledge_processing_report_builder" not in text
    assert "knowledge_structured_ingestion_service" not in text
    assert "knowledge_compilation" not in text
