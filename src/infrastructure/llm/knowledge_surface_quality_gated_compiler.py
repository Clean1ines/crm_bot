from __future__ import annotations

from src.infrastructure.llm.knowledge_surface_parallel_graph_compiler import (
    GroqParallelKnowledgeSurfaceGraphCompiler,
)


class GroqQualityGatedKnowledgeSurfaceCompiler(
    GroqParallelKnowledgeSurfaceGraphCompiler
):
    """Backward-compatible import name for the production FAQ surface graph compiler."""
