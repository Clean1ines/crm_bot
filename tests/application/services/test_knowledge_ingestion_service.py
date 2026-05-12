from unittest.mock import AsyncMock, Mock

import pytest

from src.application.errors import (
    PermanentEmbeddingProviderError,
    TransientEmbeddingProviderError,
)
from src.application.services.knowledge_ingestion_service import (
    KnowledgeIngestionService,
)
from src.domain.project_plane.knowledge_preprocessing import (
    KnowledgePreprocessingExecutionResult,
    KnowledgePreprocessingResult,
)
from src.domain.project_plane.model_usage_views import ModelUsageMeasurement


def _usage_repo() -> Mock:
    repo = Mock()
    repo.record_event = AsyncMock()
    return repo


@pytest.mark.asyncio
async def test_process_document_marks_plain_upload_processed():
    repo = Mock()
    repo.delete_document_chunks = AsyncMock()
    repo.add_knowledge_chunks = AsyncMock(return_value=2)
    repo.add_source_chunks = AsyncMock(return_value=1)
    repo.update_document_status = AsyncMock()
    repo.update_document_preprocessing_status = AsyncMock()
    usage_repo = _usage_repo()

    service = KnowledgeIngestionService(object())

    result = await service.process_document(
        project_id="project-1",
        document_id="doc-1",
        file_name="test.txt",
        chunks=[
            {"content": "First useful knowledge paragraph with enough content."},
            {"content": "Second useful knowledge paragraph with enough content."},
        ],
        mode="plain",
        knowledge_repo_factory=Mock(return_value=repo),
        model_usage_repo_factory=Mock(return_value=usage_repo),
        preprocessor_factory=None,
        logger=Mock(),
    )

    assert result.document_id == "doc-1"
    assert result.preprocessing_status == "not_requested"
    assert result.structured_entries == 0
    repo.delete_document_chunks.assert_awaited_once_with("doc-1")
    repo.add_knowledge_chunks.assert_awaited_once()
    typed_call = repo.add_knowledge_chunks.await_args.kwargs
    assert typed_call["project_id"] == "project-1"
    assert typed_call["document_id"] == "doc-1"
    assert len(typed_call["chunks"]) == 2
    assert (
        typed_call["chunks"][0].content
        == "First useful knowledge paragraph with enough content."
    )
    assert (
        typed_call["chunks"][1].content
        == "Second useful knowledge paragraph with enough content."
    )
    repo.update_document_preprocessing_status.assert_awaited_once_with(
        "doc-1",
        mode="plain",
        status="not_requested",
    )
    repo.update_document_status.assert_awaited_once_with("doc-1", "processed")
    usage_repo.record_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_document_marks_document_error_on_embedding_failure():
    repo = Mock()
    repo.delete_document_chunks = AsyncMock()
    repo.add_knowledge_chunks = AsyncMock(side_effect=RuntimeError("embed failed"))
    repo.add_source_chunks = AsyncMock(return_value=1)
    repo.update_document_status = AsyncMock()
    repo.update_document_preprocessing_status = AsyncMock()

    service = KnowledgeIngestionService(object())

    with pytest.raises(RuntimeError, match="embed failed"):
        await service.process_document(
            project_id="project-1",
            document_id="doc-err",
            file_name="test.txt",
            chunks=[{"content": "Useful knowledge paragraph with enough content."}],
            mode="plain",
            knowledge_repo_factory=Mock(return_value=repo),
            model_usage_repo_factory=Mock(return_value=_usage_repo()),
            preprocessor_factory=None,
            logger=Mock(),
        )

    repo.update_document_status.assert_awaited_once_with(
        "doc-err", "error", "embed failed"
    )


@pytest.mark.asyncio
async def test_process_document_retries_transient_embedding_provider_failure():
    repo = Mock()
    repo.delete_document_chunks = AsyncMock()
    repo.add_knowledge_chunks = AsyncMock(
        side_effect=TransientEmbeddingProviderError(
            "Embedding provider temporary failure",
            provider="voyage",
            task="document",
            model="voyage-4-lite",
            retry_after_seconds=90.0,
        )
    )
    repo.add_source_chunks = AsyncMock(return_value=1)
    repo.update_document_status = AsyncMock()
    repo.update_document_preprocessing_status = AsyncMock()

    service = KnowledgeIngestionService(object())

    with pytest.raises(TransientEmbeddingProviderError):
        await service.process_document(
            project_id="project-1",
            document_id="doc-retry",
            file_name="test.txt",
            chunks=[{"content": "Useful knowledge paragraph with enough content."}],
            mode="plain",
            knowledge_repo_factory=Mock(return_value=repo),
            model_usage_repo_factory=Mock(return_value=_usage_repo()),
            preprocessor_factory=None,
            logger=Mock(),
        )

    repo.update_document_status.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_document_marks_document_error_on_permanent_provider_failure():
    repo = Mock()
    repo.delete_document_chunks = AsyncMock()
    repo.add_knowledge_chunks = AsyncMock(
        side_effect=PermanentEmbeddingProviderError(
            "Embedding provider access denied",
            provider="voyage",
            task="document",
            model="voyage-4-lite",
        )
    )
    repo.add_source_chunks = AsyncMock(return_value=1)
    repo.update_document_status = AsyncMock()
    repo.update_document_preprocessing_status = AsyncMock()

    service = KnowledgeIngestionService(object())

    with pytest.raises(PermanentEmbeddingProviderError):
        await service.process_document(
            project_id="project-1",
            document_id="doc-perm",
            file_name="test.txt",
            chunks=[{"content": "Useful knowledge paragraph with enough content."}],
            mode="plain",
            knowledge_repo_factory=Mock(return_value=repo),
            model_usage_repo_factory=Mock(return_value=_usage_repo()),
            preprocessor_factory=None,
            logger=Mock(),
        )

    repo.update_document_status.assert_awaited_once_with(
        "doc-perm", "error", "Embedding provider access denied"
    )


@pytest.mark.asyncio
async def test_process_document_records_preprocessing_usage():
    repo = Mock()
    repo.delete_document_chunks = AsyncMock()
    repo.add_knowledge_chunks = AsyncMock(return_value=1)
    repo.add_source_chunks = AsyncMock(return_value=1)
    repo.update_document_status = AsyncMock()
    repo.update_document_preprocessing_status = AsyncMock()
    usage_repo = _usage_repo()
    measurement = ModelUsageMeasurement(
        provider="groq",
        model="llama-test",
        usage_type="llm",
        tokens_input=120,
        tokens_output=60,
        tokens_total=180,
        estimated_cost_usd=None,
        metadata={"is_estimated": False},
    )
    preprocessing_result = KnowledgePreprocessingResult(
        mode="faq",
        prompt_version="knowledge_preprocess_faq_v2",
        model="llama-test",
        entries=(),
        metrics={},
    )
    preprocessor = Mock()
    preprocessor.preprocess = AsyncMock(
        return_value=KnowledgePreprocessingExecutionResult(
            result=preprocessing_result,
            usage=measurement,
        )
    )

    service = KnowledgeIngestionService(object())

    await service.process_document(
        project_id="project-1",
        document_id="doc-usage",
        file_name="faq.txt",
        chunks=[{"content": "Useful knowledge paragraph with enough content."}],
        mode="faq",
        knowledge_repo_factory=Mock(return_value=repo),
        model_usage_repo_factory=Mock(return_value=usage_repo),
        preprocessor_factory=Mock(return_value=preprocessor),
        logger=Mock(),
    )

    usage_repo.record_event.assert_awaited_once()
    recorded_event = usage_repo.record_event.await_args.args[0]
    assert recorded_event.project_id == "project-1"
    assert recorded_event.document_id == "doc-usage"
    assert recorded_event.source == "knowledge_preprocessing"
    assert recorded_event.provider == "groq"
    assert recorded_event.model == "llama-test"
    assert recorded_event.tokens_total == 180


def test_raw_chunks_for_structured_persistence_preserves_enriched_metadata():
    from src.application.services.knowledge_ingestion_service import (
        _raw_chunks_for_structured_persistence,
    )

    raw = _raw_chunks_for_structured_persistence(
        [
            {
                "content": "## 10. Передача менеджеру\n\nАссистент передаёт диалог менеджеру при вопросах про оплату.",
                "entry_kind": "answer",
                "title": "10. Передача менеджеру",
                "source_excerpt": "Ассистент передаёт диалог менеджеру при вопросах про оплату.",
                "questions": [],
                "synonyms": [],
                "tags": ["передача", "менеджеру"],
                "embedding_text": (
                    "Title: 10. Передача менеджеру\n"
                    "Source excerpt: Ассистент передаёт диалог менеджеру при вопросах про оплату.\n"
                    "Content: ## 10. Передача менеджеру"
                ),
            }
        ]
    )

    assert raw == [
        {
            "content": "## 10. Передача менеджеру\n\nАссистент передаёт диалог менеджеру при вопросах про оплату.",
            "entry_kind": "answer",
            "title": "10. Передача менеджеру",
            "source_excerpt": "Ассистент передаёт диалог менеджеру при вопросах про оплату.",
            "questions": [],
            "synonyms": [],
            "tags": ["передача", "менеджеру"],
            "embedding_text": (
                "Title: 10. Передача менеджеру\n"
                "Source excerpt: Ассистент передаёт диалог менеджеру при вопросах про оплату.\n"
                "Content: ## 10. Передача менеджеру"
            ),
        }
    ]


def test_raw_chunks_for_structured_persistence_defaults_legacy_chunks_safely():
    from src.application.services.knowledge_ingestion_service import (
        _raw_chunks_for_structured_persistence,
    )

    raw = _raw_chunks_for_structured_persistence(
        [
            {
                "content": "Обычный текстовый chunk без metadata.",
            }
        ]
    )

    assert raw == [
        {
            "content": "Обычный текстовый chunk без metadata.",
            "entry_kind": "answer",
            "embedding_text": "Обычный текстовый chunk без metadata.",
        }
    ]
