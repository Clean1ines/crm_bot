from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.domain.project_plane.knowledge_workbench import (
    DomainInvariantError,
    KnowledgeDocument,
    KnowledgeDocumentStatus,
    KnowledgeDocumentUploadActorType,
    SourceType,
)


def test_workbench_document_preserves_donor_metadata_contract() -> None:
    now = datetime(2026, 5, 31, tzinfo=timezone.utc)

    document = KnowledgeDocument(
        document_id="document-1",
        project_id="00000000-0000-0000-0000-000000000001",
        file_name="faq.md",
        source_type=SourceType.MARKDOWN,
        content_hash="hash-1",
        upload_id="upload-1",
        file_size_bytes=123,
        status=KnowledgeDocumentStatus.SECTIONED,
        current_processing_run_id="processing-run-1",
        uploaded_by_user_id="user-1",
        uploaded_by_actor_type=KnowledgeDocumentUploadActorType.WEB_USER,
        uploaded_by_actor_id="user-1",
        trusted_upload=False,
        created_at=now,
        updated_at=now,
    )

    assert document.file_size_bytes == 123
    assert document.uploaded_by_user_id == "user-1"
    assert document.uploaded_by_actor_type is KnowledgeDocumentUploadActorType.WEB_USER
    assert document.uploaded_by_actor_id == "user-1"
    assert document.trusted_upload is False
    assert document.updated_at == now


def test_workbench_document_rejects_blank_actor_identity() -> None:
    with pytest.raises(DomainInvariantError, match="uploaded_by_user_id"):
        KnowledgeDocument(
            document_id="document-1",
            project_id="00000000-0000-0000-0000-000000000001",
            file_name="faq.md",
            source_type=SourceType.MARKDOWN,
            content_hash="hash-1",
            upload_id="upload-1",
            file_size_bytes=123,
            status=KnowledgeDocumentStatus.SECTIONED,
            uploaded_by_user_id="   ",
        )


def test_workbench_document_error_timestamp_requires_error_context() -> None:
    with pytest.raises(DomainInvariantError, match="last_error_at"):
        KnowledgeDocument(
            document_id="document-1",
            project_id="00000000-0000-0000-0000-000000000001",
            file_name="faq.md",
            source_type=SourceType.MARKDOWN,
            content_hash="hash-1",
            upload_id="upload-1",
            file_size_bytes=123,
            status=KnowledgeDocumentStatus.FAILED,
            last_error_at=datetime(2026, 5, 31, tzinfo=timezone.utc),
        )
