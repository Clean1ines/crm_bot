from __future__ import annotations

from src.infrastructure.llm.knowledge_surface_split_compiler import (
    GroqSplitKnowledgeSurfaceCompiler,
)


class GroqQualityGatedKnowledgeSurfaceCompiler(GroqSplitKnowledgeSurfaceCompiler):
    """Backward-compatible import name for the split FAQ surface compiler."""
