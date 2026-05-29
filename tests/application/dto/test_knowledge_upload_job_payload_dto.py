from __future__ import annotations

from src.application.dto.knowledge_dto import KnowledgeUploadJobPayloadDto


def test_knowledge_upload_job_payload_preserves_resume_fields() -> None:
    dto = KnowledgeUploadJobPayloadDto.from_mapping(
        {
            "project_id": "project-1",
            "document_id": "document-1",
            "file_name": "faq.md",
            "preprocessing_mode": "faq",
            "chunks": [{"content": "hello"}],
            "source": "knowledge_document_resume",
            "resume_run_id": "run-1",
        }
    )

    assert dto.source == "knowledge_document_resume"
    assert dto.resume_run_id == "run-1"
    assert dto.to_dict()["source"] == "knowledge_document_resume"
    assert dto.to_dict()["resume_run_id"] == "run-1"


def test_knowledge_upload_job_payload_omits_empty_optional_resume_fields() -> None:
    dto = KnowledgeUploadJobPayloadDto.from_mapping(
        {
            "project_id": "project-1",
            "document_id": "document-1",
            "file_name": "faq.md",
            "preprocessing_mode": "faq",
            "chunks": [{"content": "hello"}],
            "source": "   ",
            "resume_run_id": "",
        }
    )

    assert dto.source is None
    assert dto.resume_run_id is None
    assert "source" not in dto.to_dict()
    assert "resume_run_id" not in dto.to_dict()
