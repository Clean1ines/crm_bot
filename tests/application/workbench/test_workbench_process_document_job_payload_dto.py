from __future__ import annotations

import pytest

from src.application.workbench.dto import (
    WorkbenchProcessDocumentJobPayloadDto,
    WorkbenchProcessDocumentJobPayloadError,
    WorkbenchProcessDocumentJobSource,
)
from src.domain.project_plane.knowledge_workbench import (
    ProcessingMethod,
    ProcessingTrigger,
)


def test_fresh_upload_payload_contains_only_workbench_fields() -> None:
    dto = WorkbenchProcessDocumentJobPayloadDto.fresh_upload(
        project_id="project-1",
        document_id="document-1",
        processing_run_id="processing-run-1",
    )

    assert set(dto.to_queue_payload()) == {
        "project_id",
        "document_id",
        "processing_run_id",
        "processing_method",
        "trigger",
        "source",
    }


def test_workbench_payload_roundtrip_from_mapping() -> None:
    dto = WorkbenchProcessDocumentJobPayloadDto.from_mapping(
        {
            "project_id": "project-1",
            "document_id": "document-1",
            "processing_run_id": "processing-run-1",
            "processing_method": "faq_section_registry_v1",
            "trigger": "fresh_upload",
            "source": "workbench_fresh_upload",
        }
    )

    assert dto.project_id == "project-1"
    assert dto.document_id == "document-1"
    assert dto.processing_run_id == "processing-run-1"
    assert dto.processing_method is ProcessingMethod.FAQ_SECTION_REGISTRY_V1
    assert dto.trigger is ProcessingTrigger.FRESH_UPLOAD
    assert dto.source is WorkbenchProcessDocumentJobSource.FRESH_UPLOAD


def test_workbench_payload_rejects_unknown_fields() -> None:
    with pytest.raises(WorkbenchProcessDocumentJobPayloadError):
        WorkbenchProcessDocumentJobPayloadDto.from_mapping(
            {
                "project_id": "project-1",
                "document_id": "document-1",
                "processing_run_id": "processing-run-1",
                "processing_method": "faq_section_registry_v1",
                "trigger": "fresh_upload",
                "source": "workbench_fresh_upload",
                "unknown_field": "unexpected",
            }
        )


def test_workbench_payload_rejects_missing_processing_run_id() -> None:
    with pytest.raises(WorkbenchProcessDocumentJobPayloadError):
        WorkbenchProcessDocumentJobPayloadDto.from_mapping(
            {
                "project_id": "project-1",
                "document_id": "document-1",
                "processing_method": "faq_section_registry_v1",
                "trigger": "fresh_upload",
                "source": "workbench_fresh_upload",
            }
        )


def test_workbench_payload_rejects_unsupported_processing_method() -> None:
    with pytest.raises(WorkbenchProcessDocumentJobPayloadError):
        WorkbenchProcessDocumentJobPayloadDto.from_mapping(
            {
                "project_id": "project-1",
                "document_id": "document-1",
                "processing_run_id": "processing-run-1",
                "processing_method": "plain_legacy",
                "trigger": "fresh_upload",
                "source": "workbench_fresh_upload",
            }
        )


def test_explicit_user_resume_payload_uses_resume_trigger_and_source() -> None:
    dto = WorkbenchProcessDocumentJobPayloadDto.explicit_user_resume(
        project_id="project-1",
        document_id="document-1",
        processing_run_id="processing-run-1",
    )

    assert dto.processing_method is ProcessingMethod.FAQ_SECTION_REGISTRY_V1
    assert dto.trigger is ProcessingTrigger.EXPLICIT_USER_RESUME
    assert dto.source is WorkbenchProcessDocumentJobSource.EXPLICIT_USER_RESUME
    assert dto.to_queue_payload() == {
        "project_id": "project-1",
        "document_id": "document-1",
        "processing_run_id": "processing-run-1",
        "processing_method": "faq_section_registry_v1",
        "trigger": "explicit_user_resume",
        "source": "workbench_explicit_user_resume",
    }


def test_explicit_user_resume_payload_roundtrips_from_mapping() -> None:
    dto = WorkbenchProcessDocumentJobPayloadDto.from_mapping(
        {
            "project_id": "project-1",
            "document_id": "document-1",
            "processing_run_id": "processing-run-1",
            "processing_method": "faq_section_registry_v1",
            "trigger": "explicit_user_resume",
            "source": "workbench_explicit_user_resume",
        }
    )

    assert dto.trigger is ProcessingTrigger.EXPLICIT_USER_RESUME
    assert dto.source is WorkbenchProcessDocumentJobSource.EXPLICIT_USER_RESUME
