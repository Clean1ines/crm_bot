from unittest.mock import AsyncMock, Mock

import pytest

from src.application.services.knowledge_ingestion_service import KnowledgeIngestionService
from src.domain.project_plane.knowledge_preprocessing import (
    KnowledgeAnswerResolverExecutionResult,
    KnowledgePreprocessingEntry,
)
from src.domain.project_plane.retrieval_surface_compilation import (
    RetrievalSurfaceCompilationExecutionResult,
    RetrievalSurfaceCompilationResult,
    RetrievalSurfaceGraph,
)


class _FailIfPreprocessCalled:
    model_name = "legacy-preprocessor"

    async def preprocess(self, **kwargs):  # pragma: no cover
        raise AssertionError("legacy preprocess must not be called for faq/price_list")

    async def resolve_answer_cases(self, **kwargs):
        return KnowledgeAnswerResolverExecutionResult(
            mode=kwargs["mode"],
            model=self.model_name,
            prompt_version="resolver_v1",
            decisions=(),
            metrics={},
        )


class _FakeSurfaceCompiler:
    model_name = "surface-compiler"

    async def compile_surfaces(self, *, mode, source_units, file_name):
        entry = KnowledgePreprocessingEntry(
            title="Что это за продукт",
            answer="Обзор продукта",
            source_excerpt="src",
            questions=("что это за сервис?",),
            source_chunk_indexes=(0,),
        )
        graph = RetrievalSurfaceGraph(
            source_unit_keys=tuple(unit.source_unit_key for unit in source_units),
            surfaces=(),
            relations=(),
            question_ownership=(),
            metrics={"legacy_flat_preprocessor_used": False},
        )
        return RetrievalSurfaceCompilationExecutionResult(
            result=RetrievalSurfaceCompilationResult(
                mode=mode,
                prompt_version="surface_v1",
                model=self.model_name,
                graph=graph,
                projected_entries=(entry,),
                metrics={"legacy_flat_preprocessor_used": False, "projection_entry_count": 1},
            ),
            usage=None,
        )


def _repo() -> Mock:
    repo = Mock()
    repo.delete_document_chunks = AsyncMock()
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
    repo.add_canonical_entries = AsyncMock(return_value=1)
    repo.update_document_status = AsyncMock()
    repo.update_document_preprocessing_status = AsyncMock()
    repo.cancel_document_processing = AsyncMock(return_value=True)
    repo.is_document_processing_cancelled = AsyncMock(return_value=False)
    return repo


def _usage_repo() -> Mock:
    repo = Mock()
    repo.record_event = AsyncMock()
    return repo


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["faq", "price_list"])
async def test_ingestion_does_not_call_legacy_preprocess_for_surface_modes(mode: str) -> None:
    service = KnowledgeIngestionService(object())
    repo = _repo()
    surface_factory = Mock(return_value=_FakeSurfaceCompiler())

    result = await service.process_document(
        project_id="p1",
        document_id="d1",
        file_name="doc.md",
        chunks=[{"content": "## Заголовок\nТекст?", "section_title": "Заголовок", "section_body": "Текст"}],
        mode=mode,
        knowledge_repo_factory=Mock(return_value=repo),
        model_usage_repo_factory=Mock(return_value=_usage_repo()),
        preprocessor_factory=Mock(return_value=_FailIfPreprocessCalled()),
        surface_compiler_factory=surface_factory,
        logger=Mock(),
    )

    assert result.document_id == "d1"
    repo.complete_compiler_batch.assert_awaited()
    surface_factory.assert_called_once()
