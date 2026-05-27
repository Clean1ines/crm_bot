from __future__ import annotations

from collections.abc import Sequence

from src.application.services.knowledge_surface_graph_quality import (
    validate_faq_surface_graph_quality,
)
from src.domain.project_plane.knowledge_preprocessing import (
    KnowledgePreprocessingMode,
    KnowledgePreprocessingValidationError,
)
from src.domain.project_plane.retrieval_surface_compilation import (
    RetrievalSurfaceCompilationResult,
    RetrievalSurfaceSourceUnit,
)
from src.infrastructure.llm.knowledge_surface_compiler import GroqKnowledgeSurfaceCompiler


class GroqQualityGatedKnowledgeSurfaceCompiler(GroqKnowledgeSurfaceCompiler):
    """Groq surface compiler with mandatory graph quality validation.

    This keeps the current compiler API compatible with the existing ingestion service
    while preventing broken FAQ graph outputs from being marked as processed.
    """

    async def compile_surfaces(
        self,
        *,
        mode: KnowledgePreprocessingMode,
        source_units: Sequence[RetrievalSurfaceSourceUnit],
        file_name: str,
        run_id: str,
    ) -> RetrievalSurfaceCompilationResult:
        result = await super().compile_surfaces(
            mode=mode,
            source_units=source_units,
            file_name=file_name,
            run_id=run_id,
        )
        quality = validate_faq_surface_graph_quality(result.graph)
        if not quality.passed:
            raise KnowledgePreprocessingValidationError(
                "FAQ surface graph quality failed: " + ", ".join(quality.issues)
            )
        metrics = dict(result.metrics)
        metrics.update(quality.metrics)
        if quality.warnings:
            metrics["quality_warnings"] = list(quality.warnings)
        return RetrievalSurfaceCompilationResult(
            mode=result.mode,
            prompt_version=result.prompt_version,
            model=result.model,
            graph=result.graph,
            metrics=metrics,
        )
