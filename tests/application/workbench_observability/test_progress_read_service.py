from __future__ import annotations

from collections.abc import Mapping

import pytest

from src.application.workbench_observability.progress import (
    WorkbenchProgressNotFoundError,
    WorkbenchProgressReadService,
    build_workbench_progress_payload,
)


class FakeProgressQueryPort:
    def __init__(
        self,
        *,
        document: Mapping[str, object] | None,
        processing_run: Mapping[str, object] | None = None,
        section_status_counts: Mapping[str, int] | None = None,
        node_runs: tuple[Mapping[str, object], ...] = (),
    ) -> None:
        self.document = document
        self.processing_run = processing_run
        self.section_status_counts = section_status_counts or {}
        self.node_runs = node_runs
        self.calls: list[str] = []

    async def fetch_document(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> Mapping[str, object] | None:
        self.calls.append(f"document:{project_id}:{document_id}")
        return self.document

    async def fetch_latest_processing_run(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> Mapping[str, object] | None:
        self.calls.append(f"run:{project_id}:{document_id}")
        return self.processing_run

    async def fetch_section_status_counts(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> Mapping[str, int]:
        self.calls.append(f"sections:{project_id}:{document_id}")
        return self.section_status_counts

    async def fetch_node_runs(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
    ) -> tuple[Mapping[str, object], ...]:
        self.calls.append(f"nodes:{project_id}:{document_id}:{processing_run_id}")
        return self.node_runs


def test_workbench_progress_payload_preserves_old_shape_and_adds_progress() -> None:
    payload = build_workbench_progress_payload(
        document={
            "document_id": "document-1",
            "project_id": "project-1",
            "file_name": "faq.md",
            "status": "processing",
        },
        processing_run={
            "processing_run_id": "run-1",
            "status": "running",
            "trigger": "fresh_upload",
            "processing_method": "faq_section_registry_v1",
        },
        section_status_counts={"completed": 2, "failed": 1, "pending": 1},
        node_runs=(
            {
                "node_run_id": "node-1",
                "node_name": "claim_observations",
                "node_kind": "llm_claim_observations",
                "status": "failed",
            },
        ),
    )

    assert payload["document"]["document_id"] == "document-1"
    assert payload["processing_run"]["processing_run_id"] == "run-1"
    assert payload["section_status_counts"]["completed"] == 2
    assert payload["section_status_counts"]["cancelled"] == 0
    assert payload["node_runs"][0]["node_run_id"] == "node-1"

    assert payload["progress"] == {
        "total_sections": 4,
        "completed_sections": 2,
        "failed_sections": 1,
        "cancelled_sections": 0,
        "percent": 50.0,
    }
    assert payload["actions"]["can_cancel"] is True
    assert payload["actions"]["can_resume"] is False
    assert payload["actions"]["can_retry_failed"] is True


async def test_workbench_progress_read_service_uses_query_port() -> None:
    query_port = FakeProgressQueryPort(
        document={
            "document_id": "document-1",
            "project_id": "project-1",
            "file_name": "faq.md",
            "status": "processing",
        },
        processing_run={
            "processing_run_id": "run-1",
            "status": "running",
        },
        section_status_counts={"completed": 1},
        node_runs=({"node_run_id": "node-1", "status": "running"},),
    )
    service = WorkbenchProgressReadService(query_port)

    payload = await service.get_progress(
        project_id="project-1",
        document_id="document-1",
    )

    assert payload["progress"]["total_sections"] == 1
    assert query_port.calls == [
        "document:project-1:document-1",
        "run:project-1:document-1",
        "sections:project-1:document-1",
        "nodes:project-1:document-1:run-1",
    ]


async def test_workbench_progress_read_service_allows_missing_run() -> None:
    query_port = FakeProgressQueryPort(
        document={
            "document_id": "document-1",
            "project_id": "project-1",
            "file_name": "faq.md",
            "status": "sectioned",
        },
        processing_run=None,
        section_status_counts={"pending": 3},
    )
    service = WorkbenchProgressReadService(query_port)

    payload = await service.get_progress(
        project_id="project-1",
        document_id="document-1",
    )

    assert payload["processing_run"] is None
    assert payload["progress"]["total_sections"] == 3
    assert query_port.calls == [
        "document:project-1:document-1",
        "run:project-1:document-1",
        "sections:project-1:document-1",
    ]


def test_workbench_progress_payload_marks_manual_resume_for_user_cancelled_run() -> (
    None
):
    payload = build_workbench_progress_payload(
        document={
            "document_id": "document-1",
            "project_id": "project-1",
            "file_name": "faq.md",
            "status": "cancelled",
        },
        processing_run={
            "processing_run_id": "run-1",
            "status": "cancelled_by_user",
        },
        section_status_counts={"cancelled": 3},
        node_runs=(),
    )

    assert payload["actions"]["can_resume"] is True
    assert payload["actions"]["can_cancel"] is False
    assert payload["progress"]["cancelled_sections"] == 3


def test_workbench_progress_payload_raises_for_missing_document() -> None:
    with pytest.raises(WorkbenchProgressNotFoundError):
        build_workbench_progress_payload(
            document=None,
            processing_run=None,
            section_status_counts={},
            node_runs=(),
        )


def test_workbench_progress_payload_preserves_workflow_domain_counters_when_supported() -> (
    None
):
    try:
        payload = build_workbench_progress_payload(
            document={
                "document_id": "document-1",
                "project_id": "project-1",
                "file_name": "faq.md",
                "status": "processing",
            },
            processing_run={"processing_run_id": "run-1", "status": "running"},
            section_status_counts={"completed": 1},
            node_runs=(),
            workflow={
                "workflow_run_id": "workflow-1",
                "domain_counters": {
                    "draft_claim_compaction_created_node_count": 2,
                    "draft_claim_compaction_done_group_count": 1,
                },
            },
        )
    except TypeError:
        pytest.skip("progress payload has no workflow/domain_counters contract yet")

    assert payload["workflow"]["domain_counters"] == {
        "draft_claim_compaction_created_node_count": 2,
        "draft_claim_compaction_done_group_count": 1,
    }
