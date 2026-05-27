from __future__ import annotations

from src.infrastructure.llm.knowledge_surface_staged_compiler import (
    GroqStagedKnowledgeSurfaceCompiler,
)


class GroqQualityGatedKnowledgeSurfaceCompiler(GroqStagedKnowledgeSurfaceCompiler):
    """Backward-compatible import name for the staged FAQ surface graph compiler."""
