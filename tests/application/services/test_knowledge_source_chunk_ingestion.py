from unittest.mock import AsyncMock, Mock

import pytest

from src.application.services.knowledge_ingestion_service import (
    KnowledgeIngestionService,
)


def _repo() -> Mock:
    repo = Mock()
    repo.delete_document_chunks = AsyncMock()
    repo.add_source_chunks = AsyncMock(return_value=1)
    repo.add_canonical_entries = AsyncMock(return_value=1)
    repo.update_document_status = AsyncMock()
    repo.update_document_preprocessing_status = AsyncMock()
    return repo


def _usage_repo() -> Mock:
    repo = Mock()
    repo.record_event = AsyncMock()
    return repo


@pytest.mark.asyncio
async def test_process_document_persists_source_chunks_before_runtime_knowledge() -> (
    None
):
    repo = _repo()
    usage_repo = _usage_repo()
    service = KnowledgeIngestionService(object())

    result = await service.process_document(
        project_id="00000000-0000-0000-0000-000000000001",
        document_id="00000000-0000-0000-0000-000000000002",
        file_name="kb.md",
        chunks=[
            {
                "index": 3,
                "content": "Refund requests are reviewed by a human manager before approval.",
                "page": 2,
                "section_title": "Refunds",
            }
        ],
        mode="plain",
        knowledge_repo_factory=lambda pool: repo,
        model_usage_repo_factory=lambda pool: usage_repo,
        preprocessor_factory=None,
        logger=Mock(),
    )

    assert result.document_id == "00000000-0000-0000-0000-000000000002"
    repo.delete_document_chunks.assert_awaited_once_with(
        "00000000-0000-0000-0000-000000000002"
    )
    repo.add_source_chunks.assert_awaited_once()
    repo.add_canonical_entries.assert_awaited_once()

    source_call = repo.add_source_chunks.await_args.kwargs
    source_chunks = source_call["chunks"]

    assert source_call["project_id"] == "00000000-0000-0000-0000-000000000001"
    assert source_call["document_id"] == "00000000-0000-0000-0000-000000000002"
    assert len(source_chunks) == 1
    assert source_chunks[0].id == "00000000-0000-0000-0000-000000000002:3"
    assert source_chunks[0].source_index == 3
    assert source_chunks[0].content == (
        "Refund requests are reviewed by a human manager before approval."
    )
    assert source_chunks[0].page == 2
    assert source_chunks[0].section_title == "Refunds"
    assert source_chunks[0].checksum
    assert source_chunks[0].metadata["upload_chunk_index"] == 0
