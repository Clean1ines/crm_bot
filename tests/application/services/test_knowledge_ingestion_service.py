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
    KnowledgePreprocessingEntry,
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
    repo.add_canonical_entries = AsyncMock(return_value=2)
    repo.add_source_chunks = AsyncMock(return_value=1)
    repo.create_compiler_run = AsyncMock()
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
    preprocessor.merge_answer_entry = AsyncMock()

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
    preprocessor.merge_answer_entry.assert_not_awaited()


@pytest.mark.asyncio
async def test_structured_preprocessing_merges_repeated_answer_meanings():
    repo = Mock()
    repo.delete_document_chunks = AsyncMock()
    repo.add_canonical_entries = AsyncMock(return_value=1)
    repo.add_source_chunks = AsyncMock(return_value=2)
    repo.create_compiler_run = AsyncMock()
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
                title="Manager handoff",
                answer="Assistant also transfers contract questions to a human manager.",
                source_excerpt="Assistant also transfers contract questions to a human manager.",
                questions=(
                    "Who handles contract questions?",
                    "Can contracts go to a manager?",
                    "Can I ask a person about the contract?",
                ),
                synonyms=(
                    "contract manager",
                    "human contract support",
                    "manager transfer",
                    "contract handoff",
                    "operator contract",
                ),
                tags=("handoff", "contract"),
            ),
        ),
        metrics={},
    )
    first_result = KnowledgePreprocessingResult(
        mode="faq",
        prompt_version="knowledge_preprocess_faq_v2",
        model="llama-test",
        entries=(preprocessing_result.entries[0],),
        metrics={},
    )
    second_result = KnowledgePreprocessingResult(
        mode="faq",
        prompt_version="knowledge_preprocess_faq_v2",
        model="llama-test",
        entries=(preprocessing_result.entries[1],),
        metrics={},
    )
    merged_result = KnowledgePreprocessingResult(
        mode="faq",
        prompt_version="knowledge_preprocess_faq_v2",
        model="llama-test",
        entries=(
            KnowledgePreprocessingEntry(
                title="Manager handoff",
                answer=(
                    "Assistant transfers payment questions and contract "
                    "questions to a human manager."
                ),
                source_excerpt="Assistant transfers payment questions to a human manager.",
                questions=(
                    "Can I talk to a manager?",
                    "Who handles payment questions?",
                    "Who handles contract questions?",
                ),
                synonyms=(
                    "manager handoff",
                    "human manager",
                    "payment support",
                    "contract manager",
                    "operator transfer",
                ),
                tags=("handoff", "payment", "contract"),
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
    preprocessor.merge_answer_entry = AsyncMock(
        return_value=KnowledgePreprocessingExecutionResult(
            result=merged_result,
            usage=None,
        )
    )

    service = KnowledgeIngestionService(object())

    await service.process_document(
        project_id="project-1",
        document_id="doc-merge",
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
                    "## Manager handoff\n\n"
                    "Assistant also transfers contract questions to a human manager."
                )
            },
        ],
        mode="faq",
        knowledge_repo_factory=Mock(return_value=repo),
        model_usage_repo_factory=Mock(return_value=_usage_repo()),
        preprocessor_factory=Mock(return_value=preprocessor),
        logger=Mock(),
    )

    preprocessor.merge_answer_entry.assert_awaited_once()
    repo.add_canonical_entries.assert_awaited_once()
    entries = repo.add_canonical_entries.await_args.kwargs["entries"]
    assert len(entries) == 1
    entry = entries[0]
    assert entry.title == "Manager handoff"
    assert "payment questions" in entry.answer
    assert "contract questions" in entry.answer
    assert len(entry.source_refs) == 2
    assert "Who handles payment questions?" in entry.enrichment.questions
    assert "Who handles contract questions?" in entry.enrichment.questions
    assert "payment" in entry.enrichment.tags
    assert "contract" in entry.enrichment.tags


@pytest.mark.asyncio
async def test_source_sections_named_tests_or_rag_rules_are_not_discarded():
    repo = Mock()
    repo.delete_document_chunks = AsyncMock()
    repo.add_canonical_entries = AsyncMock(return_value=1)
    repo.add_source_chunks = AsyncMock(return_value=1)
    repo.create_compiler_run = AsyncMock()
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
async def test_structured_preprocessing_passes_previous_titles_between_technical_chunks():
    repo = Mock()
    repo.delete_document_chunks = AsyncMock()
    repo.add_canonical_entries = AsyncMock(return_value=2)
    repo.add_source_chunks = AsyncMock(return_value=2)
    repo.create_compiler_run = AsyncMock()
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
    preprocessor.merge_answer_entry = AsyncMock()

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

    assert first_call["previous_entry_titles"] == ()
    assert second_call["previous_entry_titles"] == ("Manager handoff",)
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
async def test_structured_preprocessing_llm_merge_preserves_both_source_excerpts():
    repo = Mock()
    repo.delete_document_chunks = AsyncMock()
    repo.add_canonical_entries = AsyncMock(return_value=1)
    repo.add_source_chunks = AsyncMock(return_value=2)
    repo.create_compiler_run = AsyncMock()
    repo.complete_compiler_run = AsyncMock()
    repo.fail_compiler_run = AsyncMock()
    repo.add_answer_candidates = AsyncMock(return_value=1)
    repo.add_candidate_clusters = AsyncMock(return_value=1)
    repo.update_document_status = AsyncMock()
    repo.update_document_preprocessing_status = AsyncMock()
    repo.cancel_document_processing = AsyncMock(return_value=True)
    repo.is_document_processing_cancelled = AsyncMock(return_value=False)

    first_entry = KnowledgePreprocessingEntry(
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
    )
    second_entry = KnowledgePreprocessingEntry(
        title="Manager handoff",
        answer="Assistant transfers contract questions to a human manager.",
        source_excerpt="Assistant transfers contract questions to a human manager.",
        questions=(
            "Who handles contract questions?",
            "Can contracts go to a manager?",
            "Can I ask a person about the contract?",
        ),
        synonyms=(
            "contract manager",
            "human contract support",
            "manager transfer",
            "contract handoff",
            "operator contract",
        ),
        tags=("handoff", "contract"),
    )
    merged_entry = KnowledgePreprocessingEntry(
        title="Manager handoff",
        answer="Assistant transfers payment and contract questions to a human manager.",
        source_excerpt="Assistant transfers payment questions to a human manager.",
        questions=(
            "Can I talk to a manager?",
            "Who handles payment questions?",
            "Who handles contract questions?",
        ),
        synonyms=(
            "manager handoff",
            "human manager",
            "payment support",
            "contract manager",
            "operator transfer",
        ),
        tags=("handoff", "payment", "contract"),
    )

    preprocessor = Mock()
    preprocessor.model_name = "llama-test"
    preprocessor.preprocess = AsyncMock(
        side_effect=[
            KnowledgePreprocessingExecutionResult(
                result=KnowledgePreprocessingResult(
                    mode="faq",
                    prompt_version="knowledge_preprocess_faq_v2",
                    model="llama-test",
                    entries=(first_entry,),
                    metrics={},
                ),
                usage=None,
            ),
            KnowledgePreprocessingExecutionResult(
                result=KnowledgePreprocessingResult(
                    mode="faq",
                    prompt_version="knowledge_preprocess_faq_v2",
                    model="llama-test",
                    entries=(second_entry,),
                    metrics={},
                ),
                usage=None,
            ),
        ]
    )
    preprocessor.merge_answer_entry = AsyncMock(
        return_value=KnowledgePreprocessingExecutionResult(
            result=KnowledgePreprocessingResult(
                mode="faq",
                prompt_version="knowledge_preprocess_faq_v2",
                model="llama-test",
                entries=(merged_entry,),
                metrics={},
            ),
            usage=None,
        )
    )

    service = KnowledgeIngestionService(object())

    await service.process_document(
        project_id="project-1",
        document_id="doc-merge-evidence",
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
                    "## Manager handoff\n\n"
                    "Assistant transfers contract questions to a human manager."
                )
            },
        ],
        mode="faq",
        knowledge_repo_factory=Mock(return_value=repo),
        model_usage_repo_factory=Mock(return_value=_usage_repo()),
        preprocessor_factory=Mock(return_value=preprocessor),
        logger=Mock(),
    )

    entries = repo.add_canonical_entries.await_args.kwargs["entries"]
    assert len(entries) == 1
    source_quotes = [source_ref.quote for source_ref in entries[0].source_refs]
    assert source_quotes == [
        "Assistant transfers payment questions to a human manager.",
        "Assistant transfers contract questions to a human manager.",
    ]
    assert entries[0].metadata["source_ref_count"] == 2


@pytest.mark.asyncio
async def test_structured_preprocessing_failure_marks_document_error():
    repo = Mock()
    repo.delete_document_chunks = AsyncMock()
    repo.add_canonical_entries = AsyncMock(return_value=1)
    repo.add_source_chunks = AsyncMock(return_value=1)
    repo.create_compiler_run = AsyncMock()
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
    preprocessor.merge_answer_entry = AsyncMock()

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
