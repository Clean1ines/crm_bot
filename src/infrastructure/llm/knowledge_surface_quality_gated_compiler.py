from __future__ import annotations

from src.infrastructure.llm.knowledge_surface_full_graph_compiler import (
    GroqFullKnowledgeSurfaceGraphCompiler,
)


class GroqQualityGatedKnowledgeSurfaceCompiler(GroqFullKnowledgeSurfaceGraphCompiler):
    """Backward-compatible import name for the full FAQ surface graph compiler."""
