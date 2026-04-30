import pytest
from unittest.mock import AsyncMock, Mock

from src.application.services.knowledge_service import KnowledgeService


class FakeJwt:
    class ExpiredSignatureError(Exception):
        pass

    class InvalidTokenError(Exception):
        pass

    @staticmethod
    def decode(token, secret, algorithms):
        assert token == "valid-token"
        assert secret == "secret"
        assert algorithms == ["HS256"]
        return {"sub": "user-1"}


@pytest.mark.asyncio
async def test_upload_accepts_real_chunker_string_chunks_and_uses_pool_repo():
    project_repo = Mock()
    project_repo.user_has_project_role = AsyncMock(return_value=True)
    project_repo.project_exists = AsyncMock(return_value=True)

    user_repo = Mock()
    user_repo.is_platform_admin = AsyncMock(return_value=False)

    pool = object()

    chunker = Mock()
    chunker.process_file = AsyncMock(return_value=["first chunk", "second chunk"])

    repo = Mock()
    repo.create_document = AsyncMock(return_value="doc-1")
    repo.add_knowledge_batch = AsyncMock(return_value=2)
    repo.update_document_status = AsyncMock()
    repo.update_document_preprocessing_status = AsyncMock()
    repo.add_structured_knowledge_batch = AsyncMock(return_value=0)
    repo.clear_project_knowledge = AsyncMock()

    chunker_factory = Mock(return_value=chunker)
    knowledge_repo_factory = Mock(return_value=repo)
    logger = Mock()

    service = KnowledgeService(project_repo, user_repo, pool, "secret", FakeJwt)

    result = await service.upload(
        "project-1",
        "test.txt",
        b"hello",
        "Bearer valid-token",
        chunker_factory=chunker_factory,
        knowledge_repo_factory=knowledge_repo_factory,
        logger=logger,
    )

    assert result.to_dict() == {
        "message": "Uploaded 2 chunks",
        "chunks": 2,
        "document_id": "doc-1",
        "preprocessing_mode": "plain",
        "preprocessing_status": "not_requested",
        "structured_entries": 0,
    }
    knowledge_repo_factory.assert_called_once_with(pool)
    repo.create_document.assert_awaited_once_with(
        project_id="project-1",
        file_name="test.txt",
        file_size=5,
        uploaded_by="user-1",
    )
    repo.add_knowledge_batch.assert_awaited_once_with(
        "project-1",
        [{"content": "first chunk"}, {"content": "second chunk"}],
        document_id="doc-1",
    )
    repo.update_document_preprocessing_status.assert_awaited_once_with(
        "doc-1",
        mode="plain",
        status="not_requested",
    )
    repo.update_document_status.assert_awaited_once_with("doc-1", "processed")


@pytest.mark.asyncio
async def test_upload_marks_document_error_when_batch_processing_fails():
    project_repo = Mock()
    project_repo.user_has_project_role = AsyncMock(return_value=True)
    project_repo.project_exists = AsyncMock(return_value=True)

    user_repo = Mock()
    user_repo.is_platform_admin = AsyncMock(return_value=False)

    pool = object()

    chunker = Mock()
    chunker.process_file = AsyncMock(return_value=["broken chunk"])

    repo = Mock()
    repo.create_document = AsyncMock(return_value="doc-err")
    repo.add_knowledge_batch = AsyncMock(side_effect=RuntimeError("embed failed"))
    repo.update_document_status = AsyncMock()
    repo.update_document_preprocessing_status = AsyncMock()
    repo.add_structured_knowledge_batch = AsyncMock(return_value=0)
    repo.clear_project_knowledge = AsyncMock()

    service = KnowledgeService(project_repo, user_repo, pool, "secret", FakeJwt)

    with pytest.raises(RuntimeError, match="embed failed"):
        await service.upload(
            "project-1",
            "test.txt",
            b"hello",
            "Bearer valid-token",
            chunker_factory=Mock(return_value=chunker),
            knowledge_repo_factory=Mock(return_value=repo),
            logger=Mock(),
        )

    repo.update_document_status.assert_awaited_once_with(
        "doc-err", "error", "embed failed"
    )


@pytest.mark.asyncio
async def test_clear_project_knowledge_uses_pool_repo():
    project_repo = Mock()
    project_repo.user_has_project_role = AsyncMock(return_value=True)
    project_repo.project_exists = AsyncMock(return_value=True)

    user_repo = Mock()
    user_repo.is_platform_admin = AsyncMock(return_value=False)

    pool = object()

    repo = Mock()
    repo.clear_project_knowledge = AsyncMock()

    knowledge_repo_factory = Mock(return_value=repo)
    logger = Mock()

    service = KnowledgeService(project_repo, user_repo, pool, "secret", FakeJwt)

    await service.clear_project_knowledge(
        "project-1",
        "Bearer valid-token",
        knowledge_repo_factory=knowledge_repo_factory,
        logger=logger,
    )

    knowledge_repo_factory.assert_called_once_with(pool)
    repo.clear_project_knowledge.assert_awaited_once_with("project-1")
