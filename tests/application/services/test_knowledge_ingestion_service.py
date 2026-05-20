from unittest.mock import AsyncMock, Mock

import pytest

from src.application.errors import (
    PermanentEmbeddingProviderError,
    TransientEmbeddingProviderError,
)
from src.application.services.knowledge_ingestion_service import (
    KnowledgeIngestionService,
)
from src.application.errors import ValidationError
from src.domain.project_plane.knowledge_preprocessing import (
    KnowledgePreprocessingEntry,
    KnowledgePreprocessingExecutionResult,
    KnowledgePreprocessingResult,
)
from src.domain.project_plane.model_usage_views import ModelUsageMeasurement


def _usage_repo() -> Mock:
    repo = Mock()
    repo.record_event = AsyncMock()
    return repo


def _knowledge_repo(*, canonical_count: int) -> Mock:
    repo = Mock()
    repo.delete_document_chunks = AsyncMock()
    repo.add_canonical_entries = AsyncMock(return_value=canonical_count)
    repo.add_source_chunks = AsyncMock(return_value=2)
    repo.create_compiler_run = AsyncMock()
    repo.create_compiler_batches = AsyncMock(return_value=0)
    repo.mark_compiler_batch_processing = AsyncMock()
    repo.complete_compiler_batch = AsyncMock()
    repo.fail_compiler_batch = AsyncMock()
    repo.complete_compiler_run = AsyncMock()
    repo.fail_compiler_run = AsyncMock()
    repo.add_answer_candidates = AsyncMock(return_value=canonical_count)
    repo.add_candidate_clusters = AsyncMock(return_value=canonical_count)
    repo.update_document_status = AsyncMock()
    repo.update_document_preprocessing_status = AsyncMock()
    repo.cancel_document_processing = AsyncMock(return_value=True)
    repo.is_document_processing_cancelled = AsyncMock(return_value=False)
    return repo


@pytest.mark.asyncio
async def test_process_document_marks_plain_upload_processed():
    repo = Mock()
    repo.delete_document_chunks = AsyncMock()
    repo.add_canonical_entries = AsyncMock(return_value=2)
    repo.add_source_chunks = AsyncMock(return_value=1)
    repo.create_compiler_run = AsyncMock()
    repo.create_compiler_batches = AsyncMock(return_value=0)
    repo.mark_compiler_batch_processing = AsyncMock()
    repo.complete_compiler_batch = AsyncMock()
    repo.fail_compiler_batch = AsyncMock()
    repo.complete_compiler_run = AsyncMock()
    repo.fail_compiler_run = AsyncMock()
    repo.add_answer_candidates = AsyncMock(return_value=1)
    repo.add_candidate_clusters = AsyncMock(return_value=1)
    repo.update_document_status = AsyncMock()
    repo.update_document_preprocessing_status = AsyncMock()
    repo.cancel_document_processing = AsyncMock(return_value=True)
    repo.is_document_processing_cancelled = AsyncMock(return_value=False)
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
    repo.add_canonical_entries.assert_awaited_once()
    typed_call = repo.add_canonical_entries.await_args.kwargs
    assert typed_call["project_id"] == "project-1"
    assert typed_call["document_id"] == "doc-1"
    assert len(typed_call["entries"]) == 2
    assert (
        typed_call["entries"][0].answer
        == "First useful knowledge paragraph with enough content."
    )
    assert (
        typed_call["entries"][1].answer
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
    repo.add_canonical_entries = AsyncMock(side_effect=RuntimeError("embed failed"))
    repo.add_source_chunks = AsyncMock(return_value=1)
    repo.create_compiler_run = AsyncMock()
    repo.create_compiler_batches = AsyncMock(return_value=0)
    repo.mark_compiler_batch_processing = AsyncMock()
    repo.complete_compiler_batch = AsyncMock()
    repo.fail_compiler_batch = AsyncMock()
    repo.complete_compiler_run = AsyncMock()
    repo.fail_compiler_run = AsyncMock()
    repo.add_answer_candidates = AsyncMock(return_value=1)
    repo.add_candidate_clusters = AsyncMock(return_value=1)
    repo.update_document_status = AsyncMock()
    repo.update_document_preprocessing_status = AsyncMock()
    repo.cancel_document_processing = AsyncMock(return_value=True)
    repo.is_document_processing_cancelled = AsyncMock(return_value=False)

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
    repo.add_canonical_entries = AsyncMock(
        side_effect=TransientEmbeddingProviderError(
            "Embedding provider temporary failure",
            provider="voyage",
            task="document",
            model="voyage-4-lite",
            retry_after_seconds=90.0,
        )
    )
    repo.add_source_chunks = AsyncMock(return_value=1)
    repo.create_compiler_run = AsyncMock()
    repo.create_compiler_batches = AsyncMock(return_value=0)
    repo.mark_compiler_batch_processing = AsyncMock()
    repo.complete_compiler_batch = AsyncMock()
    repo.fail_compiler_batch = AsyncMock()
    repo.complete_compiler_run = AsyncMock()
    repo.fail_compiler_run = AsyncMock()
    repo.add_answer_candidates = AsyncMock(return_value=1)
    repo.add_candidate_clusters = AsyncMock(return_value=1)
    repo.update_document_status = AsyncMock()
    repo.update_document_preprocessing_status = AsyncMock()
    repo.cancel_document_processing = AsyncMock(return_value=True)
    repo.is_document_processing_cancelled = AsyncMock(return_value=False)

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
    repo.add_canonical_entries = AsyncMock(
        side_effect=PermanentEmbeddingProviderError(
            "Embedding provider access denied",
            provider="voyage",
            task="document",
            model="voyage-4-lite",
        )
    )
    repo.add_source_chunks = AsyncMock(return_value=1)
    repo.create_compiler_run = AsyncMock()
    repo.create_compiler_batches = AsyncMock(return_value=0)
    repo.mark_compiler_batch_processing = AsyncMock()
    repo.complete_compiler_batch = AsyncMock()
    repo.fail_compiler_batch = AsyncMock()
    repo.complete_compiler_run = AsyncMock()
    repo.fail_compiler_run = AsyncMock()
    repo.add_answer_candidates = AsyncMock(return_value=1)
    repo.add_candidate_clusters = AsyncMock(return_value=1)
    repo.update_document_status = AsyncMock()
    repo.update_document_preprocessing_status = AsyncMock()
    repo.cancel_document_processing = AsyncMock(return_value=True)
    repo.is_document_processing_cancelled = AsyncMock(return_value=False)

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
    repo.add_canonical_entries = AsyncMock(return_value=1)
    repo.add_source_chunks = AsyncMock(return_value=1)
    repo.create_compiler_run = AsyncMock()
    repo.create_compiler_batches = AsyncMock(return_value=0)
    repo.mark_compiler_batch_processing = AsyncMock()
    repo.complete_compiler_batch = AsyncMock()
    repo.fail_compiler_batch = AsyncMock()
    repo.complete_compiler_run = AsyncMock()
    repo.fail_compiler_run = AsyncMock()
    repo.add_answer_candidates = AsyncMock(return_value=1)
    repo.add_candidate_clusters = AsyncMock(return_value=1)
    repo.update_document_status = AsyncMock()
    repo.update_document_preprocessing_status = AsyncMock()
    repo.cancel_document_processing = AsyncMock(return_value=True)
    repo.is_document_processing_cancelled = AsyncMock(return_value=False)
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
        entries=(
            KnowledgePreprocessingEntry(
                title="Manager handoff",
                answer="Assistant transfers payment questions to a human manager.",
                source_excerpt="Assistant transfers payment questions to a human manager.",
                questions=(
                    "Can I talk to a manager?",
                    "Who handles payment questions?",
                    "Can support transfer me?",
                ),
                synonyms=(
                    "manager handoff",
                    "human manager",
                    "payment support",
                    "operator transfer",
                    "human support",
                ),
                tags=("handoff", "payment"),
            ),
        ),
        metrics={},
    )
    preprocessor = Mock()
    preprocessor.model_name = "llama-test"
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


@pytest.mark.asyncio
async def test_structured_preprocessing_persists_only_answer_entries():
    repo = Mock()
    repo.delete_document_chunks = AsyncMock()
    repo.add_canonical_entries = AsyncMock(return_value=2)
    repo.add_source_chunks = AsyncMock(return_value=3)
    repo.create_compiler_run = AsyncMock()
    repo.create_compiler_batches = AsyncMock(return_value=0)
    repo.mark_compiler_batch_processing = AsyncMock()
    repo.complete_compiler_batch = AsyncMock()
    repo.fail_compiler_batch = AsyncMock()
    repo.complete_compiler_run = AsyncMock()
    repo.fail_compiler_run = AsyncMock()
    repo.add_answer_candidates = AsyncMock(return_value=2)
    repo.add_candidate_clusters = AsyncMock(return_value=2)
    repo.update_document_status = AsyncMock()
    repo.update_document_preprocessing_status = AsyncMock()
    repo.cancel_document_processing = AsyncMock(return_value=True)
    repo.is_document_processing_cancelled = AsyncMock(return_value=False)

    preprocessing_result = KnowledgePreprocessingResult(
        mode="faq",
        prompt_version="knowledge_preprocess_faq_v2",
        model="llama-test",
        entries=(
            KnowledgePreprocessingEntry(
                title="Manager handoff",
                answer="Assistant transfers payment questions to a human manager.",
                source_excerpt="Assistant transfers payment questions to a human manager.",
                questions=(
                    "Can I talk to a manager?",
                    "Who handles payment questions?",
                    "Can support transfer me?",
                ),
                synonyms=(
                    "manager handoff",
                    "human manager",
                    "payment support",
                    "operator transfer",
                    "human support",
                ),
                tags=("handoff", "payment"),
            ),
            KnowledgePreprocessingEntry(
                title="Document search",
                answer="The assistant searches uploaded knowledge before answering.",
                source_excerpt="The assistant searches uploaded knowledge before answering.",
                questions=(
                    "How does document search work?",
                    "Does the assistant search knowledge?",
                    "Where does the answer come from?",
                ),
                synonyms=(
                    "document search",
                    "knowledge search",
                    "rag search",
                    "uploaded knowledge",
                    "source answer",
                ),
                tags=("rag", "search"),
            ),
        ),
        metrics={"source": "unit-test"},
    )
    empty_preprocessing_result = KnowledgePreprocessingResult(
        mode="faq",
        prompt_version="knowledge_preprocess_faq_v2",
        model="llama-test",
        entries=(),
        metrics={},
    )
    preprocessor = Mock()
    preprocessor.model_name = "llama-test"
    preprocessor.preprocess = AsyncMock(
        side_effect=[
            KnowledgePreprocessingExecutionResult(
                result=preprocessing_result,
                usage=None,
            ),
            KnowledgePreprocessingExecutionResult(
                result=empty_preprocessing_result,
                usage=None,
            ),
            KnowledgePreprocessingExecutionResult(
                result=empty_preprocessing_result,
                usage=None,
            ),
        ]
    )

    service = KnowledgeIngestionService(object())

    result = await service.process_document(
        project_id="project-1",
        document_id="doc-k1",
        file_name="kb.md",
        chunks=[
            {
                "content": (
                    "## Manager handoff\n\n"
                    "Assistant transfers payment questions to a human manager."
                )
            },
            {
                "content": (
                    "## Document search\n\n"
                    "The assistant searches uploaded knowledge before answering."
                )
            },
            {"content": "Raw technical chunk that must not become a runtime row."},
        ],
        mode="faq",
        knowledge_repo_factory=Mock(return_value=repo),
        model_usage_repo_factory=Mock(return_value=_usage_repo()),
        preprocessor_factory=Mock(return_value=preprocessor),
        logger=Mock(),
    )

    assert result.preprocessing_status == "completed"
    assert result.structured_entries == 2

    repo.add_source_chunks.assert_awaited_once()
    source_call = repo.add_source_chunks.await_args.kwargs
    assert len(source_call["chunks"]) == 3

    repo.add_canonical_entries.assert_awaited_once()
    canonical_call = repo.add_canonical_entries.await_args.kwargs
    entries = canonical_call["entries"]
    assert len(entries) == 2
    assert [entry.title for entry in entries] == [
        "Manager handoff",
        "Document search",
    ]
    assert all(
        entry.compiler_version == "kcd_v1_stage_k_answer_compiler" for entry in entries
    )
    assert all(entry.has_source_refs for entry in entries)
    assert all(entry.entry_kind.value == "faq_answer" for entry in entries)
    assert all(
        "Raw technical chunk that must not become a runtime row." not in entry.answer
        for entry in entries
    )
    assert entries[0].enrichment.questions == (
        "Can I talk to a manager?",
        "Who handles payment questions?",
        "Can support transfer me?",
    )
    assert entries[0].enrichment.synonyms == (
        "manager handoff",
        "human manager",
        "payment support",
        "operator transfer",
        "human support",
    )


@pytest.mark.asyncio
async def test_source_sections_named_tests_or_rag_rules_are_not_discarded():
    repo = Mock()
    repo.delete_document_chunks = AsyncMock()
    repo.add_canonical_entries = AsyncMock(return_value=1)
    repo.add_source_chunks = AsyncMock(return_value=1)
    repo.create_compiler_run = AsyncMock()
    repo.create_compiler_batches = AsyncMock(return_value=0)
    repo.mark_compiler_batch_processing = AsyncMock()
    repo.complete_compiler_batch = AsyncMock()
    repo.fail_compiler_batch = AsyncMock()
    repo.complete_compiler_run = AsyncMock()
    repo.fail_compiler_run = AsyncMock()
    repo.add_answer_candidates = AsyncMock(return_value=1)
    repo.add_candidate_clusters = AsyncMock(return_value=1)
    repo.update_document_status = AsyncMock()
    repo.update_document_preprocessing_status = AsyncMock()
    repo.cancel_document_processing = AsyncMock(return_value=True)
    repo.is_document_processing_cancelled = AsyncMock(return_value=False)

    preprocessing_result = KnowledgePreprocessingResult(
        mode="faq",
        prompt_version="knowledge_preprocess_faq_v2",
        model="llama-test",
        entries=(
            KnowledgePreprocessingEntry(
                title="Negative tests and RAG rules",
                answer=(
                    "Negative scenarios describe when the assistant should not "
                    "answer without grounded knowledge."
                ),
                source_excerpt=(
                    "Negative scenarios describe when the assistant should not "
                    "answer without grounded knowledge."
                ),
                questions=(
                    "When should the assistant not answer?",
                    "What are negative RAG scenarios?",
                    "How should the knowledge base be tested?",
                ),
                synonyms=(
                    "negative tests",
                    "rag rules",
                    "do not answer",
                    "grounded knowledge only",
                    "knowledge base testing",
                ),
                tags=("rag", "testing"),
            ),
        ),
        metrics={},
    )
    preprocessor = Mock()
    preprocessor.model_name = "llama-test"
    preprocessor.preprocess = AsyncMock(
        return_value=KnowledgePreprocessingExecutionResult(
            result=preprocessing_result,
            usage=None,
        )
    )

    service = KnowledgeIngestionService(object())

    await service.process_document(
        project_id="project-1",
        document_id="doc-rag-rules",
        file_name="kb.md",
        chunks=[
            {
                "content": (
                    "## Negative tests and RAG rules\n\n"
                    "Negative scenarios describe when the assistant should not "
                    "answer without grounded knowledge."
                )
            }
        ],
        mode="faq",
        knowledge_repo_factory=Mock(return_value=repo),
        model_usage_repo_factory=Mock(return_value=_usage_repo()),
        preprocessor_factory=Mock(return_value=preprocessor),
        logger=Mock(),
    )

    entries = repo.add_canonical_entries.await_args.kwargs["entries"]
    assert len(entries) == 1
    assert entries[0].title == "Negative tests and RAG rules"
    assert entries[0].entry_kind.value == "faq_answer"
    assert entries[0].visibility.value == "runtime"
    assert entries[0].has_source_refs


@pytest.mark.asyncio
async def test_structured_preprocessing_does_not_pass_known_question_intents_between_technical_chunks():
    repo = Mock()
    repo.delete_document_chunks = AsyncMock()
    repo.add_canonical_entries = AsyncMock(return_value=2)
    repo.add_source_chunks = AsyncMock(return_value=2)
    repo.create_compiler_run = AsyncMock()
    repo.create_compiler_batches = AsyncMock(return_value=0)
    repo.mark_compiler_batch_processing = AsyncMock()
    repo.complete_compiler_batch = AsyncMock()
    repo.fail_compiler_batch = AsyncMock()
    repo.complete_compiler_run = AsyncMock()
    repo.fail_compiler_run = AsyncMock()
    repo.add_answer_candidates = AsyncMock(return_value=2)
    repo.add_candidate_clusters = AsyncMock(return_value=2)
    repo.update_document_status = AsyncMock()
    repo.update_document_preprocessing_status = AsyncMock()
    repo.cancel_document_processing = AsyncMock(return_value=True)
    repo.is_document_processing_cancelled = AsyncMock(return_value=False)

    first_result = KnowledgePreprocessingResult(
        mode="faq",
        prompt_version="knowledge_preprocess_faq_v2",
        model="llama-test",
        entries=(
            KnowledgePreprocessingEntry(
                title="Manager handoff",
                answer="Assistant transfers payment questions to a human manager.",
                source_excerpt="Assistant transfers payment questions to a human manager.",
                questions=(
                    "Can I talk to a manager?",
                    "Who handles payment questions?",
                    "Can support transfer me?",
                ),
                synonyms=(
                    "manager handoff",
                    "human manager",
                    "payment support",
                    "operator transfer",
                    "human support",
                ),
                tags=("handoff", "payment"),
            ),
        ),
        metrics={},
    )
    second_result = KnowledgePreprocessingResult(
        mode="faq",
        prompt_version="knowledge_preprocess_faq_v2",
        model="llama-test",
        entries=(
            KnowledgePreprocessingEntry(
                title="Document search",
                answer="The assistant searches uploaded knowledge before answering.",
                source_excerpt="The assistant searches uploaded knowledge before answering.",
                questions=(
                    "How does document search work?",
                    "Does the assistant search knowledge?",
                    "Where does the answer come from?",
                ),
                synonyms=(
                    "document search",
                    "knowledge search",
                    "rag search",
                    "uploaded knowledge",
                    "source answer",
                ),
                tags=("rag", "search"),
            ),
        ),
        metrics={},
    )

    preprocessor = Mock()
    preprocessor.model_name = "llama-test"
    preprocessor.preprocess = AsyncMock(
        side_effect=[
            KnowledgePreprocessingExecutionResult(result=first_result, usage=None),
            KnowledgePreprocessingExecutionResult(result=second_result, usage=None),
        ]
    )

    service = KnowledgeIngestionService(object())

    result = await service.process_document(
        project_id="project-1",
        document_id="doc-carry",
        file_name="kb.md",
        chunks=[
            {
                "content": (
                    "## Manager handoff\n\n"
                    "Assistant transfers payment questions to a human manager."
                )
            },
            {
                "content": (
                    "## Document search\n\n"
                    "The assistant searches uploaded knowledge before answering."
                )
            },
        ],
        mode="faq",
        knowledge_repo_factory=Mock(return_value=repo),
        model_usage_repo_factory=Mock(return_value=_usage_repo()),
        preprocessor_factory=Mock(return_value=preprocessor),
        logger=Mock(),
    )

    assert result.structured_entries == 2
    assert preprocessor.preprocess.await_count == 2

    first_call = preprocessor.preprocess.await_args_list[0].kwargs
    second_call = preprocessor.preprocess.await_args_list[1].kwargs

    assert "previous_entry_titles" not in first_call
    assert "previous_entry_titles" not in second_call
    assert "previous_question_intents" not in first_call
    assert "previous_question_intents" not in second_call
    assert len(first_call["chunks"]) == 1
    assert len(second_call["chunks"]) == 1

    entries = repo.add_canonical_entries.await_args.kwargs["entries"]
    assert [entry.title for entry in entries] == [
        "Manager handoff",
        "Document search",
    ]
    assert all(
        entry.compiler_version == "kcd_v1_stage_k_answer_compiler" for entry in entries
    )


@pytest.mark.asyncio
async def test_structured_preprocessing_exact_duplicate_fragments_merge_with_source_evidence():
    repo = _knowledge_repo(canonical_count=1)
    duplicate_entry = KnowledgePreprocessingEntry(
        title="Manager handoff",
        answer="Assistant transfers payment questions to a human manager.",
        source_excerpt="Assistant transfers payment questions to a human manager.",
        questions=(
            "Can I talk to a manager?",
            "Who handles payment questions?",
        ),
        synonyms=("manager handoff", "human manager"),
        tags=("handoff",),
        canonical_question="Can I talk to a manager?",
    )
    first_result = KnowledgePreprocessingResult(
        mode="faq",
        prompt_version="knowledge_answer_compiler_faq_v1",
        model="llama-test",
        entries=(duplicate_entry,),
        metrics={},
    )
    second_result = KnowledgePreprocessingResult(
        mode="faq",
        prompt_version="knowledge_answer_compiler_faq_v1",
        model="llama-test",
        entries=(duplicate_entry,),
        metrics={},
    )
    preprocessor = Mock()
    preprocessor.model_name = "llama-test"
    preprocessor.preprocess = AsyncMock(
        side_effect=[
            KnowledgePreprocessingExecutionResult(result=first_result, usage=None),
            KnowledgePreprocessingExecutionResult(result=second_result, usage=None),
        ]
    )

    result = await KnowledgeIngestionService(object()).process_document(
        project_id="project-1",
        document_id="doc-duplicate-evidence",
        file_name="faq.md",
        chunks=[
            {"content": "Assistant transfers payment questions to a human manager."},
            {"content": "Assistant transfers payment questions to a human manager."},
        ],
        mode="faq",
        knowledge_repo_factory=Mock(return_value=repo),
        model_usage_repo_factory=Mock(return_value=_usage_repo()),
        preprocessor_factory=Mock(return_value=preprocessor),
        logger=Mock(),
    )

    assert result.structured_entries == 1
    repo.create_compiler_batches.assert_awaited_once()
    assert len(repo.create_compiler_batches.await_args.kwargs["batches"]) == 2
    assert repo.mark_compiler_batch_processing.await_count == 2
    assert repo.complete_compiler_batch.await_count == 2
    assert repo.fail_compiler_batch.await_count == 0
    assert repo.add_answer_candidates.await_count == 3
    raw_candidates = repo.add_answer_candidates.await_args_list[0].kwargs["candidates"]
    assert raw_candidates[0].metadata["stage"] == "stage_k_raw_extraction"
    assert raw_candidates[0].metadata["batch_index"] == 1
    entries = repo.add_canonical_entries.await_args.kwargs["entries"]
    assert len(entries) == 1
    assert entries[0].source_refs[0].quote == duplicate_entry.source_excerpt
    assert entries[0].metadata["merged_preprocessing_entry_count"] == 2
    assert entries[0].metadata["source_ref_count"] == 1


@pytest.mark.asyncio
async def test_structured_preprocessing_failure_marks_document_error():
    repo = Mock()
    repo.delete_document_chunks = AsyncMock()
    repo.add_canonical_entries = AsyncMock(return_value=1)
    repo.add_source_chunks = AsyncMock(return_value=1)
    repo.create_compiler_run = AsyncMock()
    repo.create_compiler_batches = AsyncMock(return_value=0)
    repo.mark_compiler_batch_processing = AsyncMock()
    repo.complete_compiler_batch = AsyncMock()
    repo.fail_compiler_batch = AsyncMock()
    repo.complete_compiler_run = AsyncMock()
    repo.fail_compiler_run = AsyncMock()
    repo.add_answer_candidates = AsyncMock(return_value=1)
    repo.add_candidate_clusters = AsyncMock(return_value=1)
    repo.update_document_status = AsyncMock()
    repo.update_document_preprocessing_status = AsyncMock()
    repo.cancel_document_processing = AsyncMock(return_value=True)
    repo.is_document_processing_cancelled = AsyncMock(return_value=False)

    preprocessor = Mock()
    preprocessor.model_name = "llama-test"
    preprocessor.preprocess = AsyncMock(
        side_effect=ValueError("Invalid preprocessing JSON: Extra data")
    )

    service = KnowledgeIngestionService(object())

    with pytest.raises(Exception, match="Invalid preprocessing JSON: Extra data"):
        await service.process_document(
            project_id="project-1",
            document_id="doc-json-failure",
            file_name="faq.txt",
            chunks=[{"content": "Useful knowledge paragraph with enough content."}],
            mode="faq",
            knowledge_repo_factory=Mock(return_value=repo),
            model_usage_repo_factory=Mock(return_value=_usage_repo()),
            preprocessor_factory=Mock(return_value=preprocessor),
            logger=Mock(),
        )
    repo.update_document_status.assert_awaited_with(
        "doc-json-failure",
        "error",
        "Invalid preprocessing JSON: Extra data",
    )

    repo.update_document_status.assert_awaited()


def test_online_pipeline_defaults_to_parallel_extraction_and_merge_enabled():
    from pathlib import Path
    import src.application.services.knowledge_ingestion_service as service_module

    source = Path(service_module.__file__).read_text()
    assert service_module.KCD_STAGE_K_EXTRACTION_CONCURRENCY_DEFAULT == 3
    assert "asyncio.Semaphore(extraction_concurrency)" in source
    assert 'preprocessing_metrics["answer_resolution_enabled"] = True' in source
    assert "answer_resolution_failed" in source


def test_online_pipeline_publishes_tightened_entries_after_raw_candidates_are_saved():
    from pathlib import Path
    import src.application.services.knowledge_ingestion_service as service_module

    source = Path(service_module.__file__).read_text()
    raw_save_index = source.index("await repo.add_answer_candidates")
    merge_index = source.index("await _resolve_compiled_answer_cases", raw_save_index)
    publish_index = source.index(
        "canonical_entries = _canonical_entries_from_preprocessing_result",
        merge_index,
    )

    assert raw_save_index < merge_index < publish_index
    assert "entries=tightened_entries" in source[merge_index:publish_index]
    assert "entries=compiled_entries" not in source[merge_index:publish_index]


def test_resume_processing_uses_shared_post_extraction_pipeline():
    from pathlib import Path
    import src.application.services.knowledge_ingestion_service as service_module

    source = Path(service_module.__file__).read_text()
    resume_idx = source.index("async def resume_processing")
    assert "_run_answer_resolution_publication_pipeline(" in source[resume_idx:]


def test_resume_processing_does_not_call_canonical_entries_from_raw_answer_candidates_directly():
    from pathlib import Path
    import src.application.services.knowledge_ingestion_service as service_module

    source = Path(service_module.__file__).read_text()
    resume_block = source[source.index("async def resume_processing") : source.index("async def retry_failed_batches")]
    assert "_canonical_entries_from_raw_answer_candidates(" not in resume_block


def test_process_document_uses_shared_post_extraction_pipeline():
    from pathlib import Path
    import src.application.services.knowledge_ingestion_service as service_module

    source = Path(service_module.__file__).read_text()
    process_block = source[source.index("async def process_document") :]
    assert "_run_answer_resolution_publication_pipeline(" in process_block


@pytest.mark.anyio
async def test_resume_processing_rejects_failed_batches():
    service = KnowledgeIngestionService(object())
    repo = Mock()
    repo.get_document = AsyncMock(return_value=type("D", (), {"project_id": "p1", "preprocessing_mode": "faq", "preprocessing_metrics": {"stage": "answer_resolution_pending"}, "file_name": "a.md", "preprocessing_prompt_version": "v1", "preprocessing_model": "m"})())
    repo.list_document_source_chunks = AsyncMock(return_value=[Mock()])
    repo.list_document_compiler_batches = AsyncMock(return_value=[type("B", (), {"status": "failed"})()])
    with pytest.raises(ValidationError):
        await service.resume_processing(project_id="p1", document_id="d1", knowledge_repo_factory=Mock(return_value=repo), logger=Mock())


@pytest.mark.anyio
async def test_resume_processing_rejects_pending_or_processing_batches():
    service = KnowledgeIngestionService(object())
    repo = Mock()
    repo.get_document = AsyncMock(return_value=type("D", (), {"project_id": "p1", "preprocessing_mode": "faq", "preprocessing_metrics": {"stage": "answer_resolution_pending"}, "file_name": "a.md", "preprocessing_prompt_version": "v1", "preprocessing_model": "m"})())
    repo.list_document_source_chunks = AsyncMock(return_value=[Mock()])
    repo.list_document_compiler_batches = AsyncMock(return_value=[type("B", (), {"status": "processing"})()])
    with pytest.raises(ValidationError):
        await service.resume_processing(project_id="p1", document_id="d1", knowledge_repo_factory=Mock(return_value=repo), logger=Mock())


@pytest.mark.anyio
async def test_resume_processing_rejects_no_raw_candidates():
    service = KnowledgeIngestionService(object())
    repo = Mock()
    repo.get_document = AsyncMock(return_value=type("D", (), {"project_id": "p1", "preprocessing_mode": "faq", "preprocessing_metrics": {"stage": "answer_resolution_pending"}, "file_name": "a.md", "preprocessing_prompt_version": "v1", "preprocessing_model": "m"})())
    repo.list_document_source_chunks = AsyncMock(return_value=[Mock()])
    repo.list_document_compiler_batches = AsyncMock(return_value=[type("B", (), {"status": "completed"})()])
    repo.list_document_raw_answer_candidates = AsyncMock(return_value=[])
    with pytest.raises(ValidationError):
        await service.resume_processing(project_id="p1", document_id="d1", knowledge_repo_factory=Mock(return_value=repo), logger=Mock())


@pytest.mark.anyio
async def test_resume_processing_rejects_ambiguous_compiler_run():
    service = KnowledgeIngestionService(object())
    repo = Mock()
    repo.get_document = AsyncMock(return_value=type("D", (), {"project_id": "p1", "preprocessing_mode": "faq", "preprocessing_metrics": {"stage": "answer_resolution_pending"}, "file_name": "a.md", "preprocessing_prompt_version": "v1", "preprocessing_model": "m"})())
    repo.list_document_source_chunks = AsyncMock(return_value=[Mock()])
    repo.list_document_compiler_batches = AsyncMock(return_value=[type("B", (), {"status": "completed"})()])
    c1 = type("C", (), {"compiler_run_id": "r1", "title": "t", "candidate_answer": "a", "source_refs": ()})()
    c2 = type("C", (), {"compiler_run_id": "r2", "title": "t", "candidate_answer": "a", "source_refs": ()})()
    repo.list_document_raw_answer_candidates = AsyncMock(return_value=[c1, c2])
    with pytest.raises(ValidationError):
        await service.resume_processing(project_id="p1", document_id="d1", knowledge_repo_factory=Mock(return_value=repo), logger=Mock())


def test_mechanical_cleanup_dedupes_exact_question_variants_without_semantic_dictionary():
    from src.application.services.knowledge_ingestion_service import (
        _mechanically_cleanup_compiled_entries,
    )

    entry = KnowledgePreprocessingEntry(
        title="Возврат средств",
        answer="Возврат оформляется через менеджера.",
        source_excerpt="Возврат оформляется через менеджера.",
        questions=("Как оформить возврат?", " Как оформить возврат? "),
        synonyms=("Возврат", "возврат"),
        tags=("refund", "refund"),
        canonical_question="Как оформить возврат?",
    )

    result = _mechanically_cleanup_compiled_entries(
        entries=(entry, entry),
        source_excerpts_by_entry=((entry.source_excerpt,), (entry.source_excerpt,)),
    )

    assert len(result.entries) == 1
    assert result.entries[0].questions == ("Как оформить возврат?",)
    assert result.entries[0].synonyms == ("Возврат",)
    assert result.entries[0].tags == ("refund",)
    assert result.metrics["exact_duplicate_candidate_collapse_count"] == 1
    assert result.metrics["deduped_question_variant_count"] == 0


def test_online_ingestion_merge_logic_has_no_meta_question_filter_dictionary():
    from pathlib import Path
    import src.application.services.knowledge_ingestion_service as service_module

    source = Path(service_module.__file__).read_text()
    online_section = source[
        source.index("def _mechanically_cleanup_compiled_entries") : source.index(
            "async def _existing_project_titles_for_answer_resolution"
        )
    ]

    forbidden_snippets = (
        "suspicious_meta",
        "meta_entry",
        "Возможные вопросы пользователей",
        "служеб",
        "метавопрос",
    )
    assert all(snippet not in online_section for snippet in forbidden_snippets)


def test_answer_resolution_uses_only_resolver_answer_and_deterministic_fields():
    from src.application.services.knowledge_ingestion_service import (
        _apply_answer_resolution_decisions,
    )
    from src.domain.project_plane.knowledge_preprocessing import (
        KnowledgeAnswerResolutionDecision,
    )

    entries = (
        KnowledgePreprocessingEntry(
            title="Возврат",
            answer="Условия возврата зависят от ситуации и этапа работы.",
            source_excerpt="Условия возврата зависят от ситуации и этапа работы.",
            questions=("Как оформить возврат?",),
            synonyms=("возврат",),
            tags=("refund",),
            source_chunk_indexes=(0,),
        ),
        KnowledgePreprocessingEntry(
            title="Возврат средств",
            answer="Условия возврата средств зависят от ситуации.",
            source_excerpt="Условия возврата средств зависят от ситуации.",
            questions=("Можно вернуть оплату?",),
            synonyms=("возврат средств",),
            tags=("billing",),
            source_chunk_indexes=(1,),
        ),
    )
    decision = KnowledgeAnswerResolutionDecision(
        case_id="group-1",
        action="merge",
        candidate_ids=("entry-0", "entry-1"),
        canonical_answer="Условия возврата зависят от ситуации и этапа работы.",
    )

    tightened, source_excerpts = _apply_answer_resolution_decisions(
        entries=entries,
        decisions=(decision,),
        source_excerpts_by_entry=(
            (entries[0].source_excerpt,),
            (entries[1].source_excerpt,),
        ),
    )

    assert len(tightened) == 1
    assert tightened[0].answer == "Условия возврата зависят от ситуации и этапа работы."
    assert "Условия возврата средств зависят от ситуации." not in tightened[0].answer
    assert tightened[0].questions == (
        "Как оформить возврат?",
        "Можно вернуть оплату?",
    )
    assert tightened[0].synonyms == ("возврат", "возврат средств")
    assert tightened[0].tags == ("refund", "billing")
    assert tightened[0].source_chunk_indexes == (0, 1)
    assert len(source_excerpts[0]) == 2


def test_keep_separate_answer_resolution_does_not_delete_answer_entry():
    from src.application.services.knowledge_ingestion_service import (
        _apply_answer_resolution_decisions,
    )
    from src.domain.project_plane.knowledge_preprocessing import (
        KnowledgeAnswerResolutionDecision,
    )

    entry = KnowledgePreprocessingEntry(
        title="Internal instruction",
        answer="Каждая тема должна быть отделена от других.",
        source_excerpt="Каждая тема должна быть отделена от других.",
        questions=("Как оформлять темы?",),
    )
    decision = KnowledgeAnswerResolutionDecision(
        case_id="group-1",
        action="keep_separate",
        candidate_ids=("entry-0",),
        reason="not the same answer intent",
        confidence=0.7,
    )

    tightened, _ = _apply_answer_resolution_decisions(
        entries=(entry,),
        decisions=(decision,),
    )

    assert tightened == (entry,)


def test_publication_guard_collapses_exact_duplicate_answers():
    from src.application.services.knowledge_ingestion_service import (
        _canonical_entries_from_preprocessing_result,
    )
    from src.domain.project_plane.knowledge_compilation import SourceChunk
    from src.domain.project_plane.knowledge_preprocessing import (
        KnowledgePreprocessingResult,
    )

    result = KnowledgePreprocessingResult(
        mode="faq",
        prompt_version="knowledge_answer_compiler_faq_v1",
        model="llama-test",
        entries=(
            KnowledgePreprocessingEntry(
                title="Правило ответа",
                answer="Ассистент не выдумывает ответ.",
                source_excerpt="Ассистент не выдумывает ответ.",
                questions=("Что делает ассистент без данных?",),
            ),
            KnowledgePreprocessingEntry(
                title="Ответ без данных",
                answer="Ассистент не выдумывает ответ.",
                source_excerpt="Ассистент не выдумывает ответ.",
                questions=("Как отвечает ассистент без данных?",),
            ),
        ),
    )
    source_chunk = SourceChunk(
        id="chunk-1",
        document_id="doc-1",
        project_id="project-1",
        source_index=0,
        content="Ассистент не выдумывает ответ.",
    )

    entries = _canonical_entries_from_preprocessing_result(
        project_id="project-1",
        document_id="doc-1",
        compiler_run_id="run-1",
        result=result,
        source_chunks=(source_chunk,),
    )

    assert len(entries) == 1
    assert entries[0].enrichment.questions == (
        "Что делает ассистент без данных?",
        "Как отвечает ассистент без данных?",
    )
