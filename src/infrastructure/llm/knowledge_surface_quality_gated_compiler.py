from __future__ import annotations

from collections.abc import Mapping

from src.infrastructure.llm.knowledge_surface_parallel_graph_compiler import (
    GroqParallelKnowledgeSurfaceGraphCompiler,
)


class GroqQualityGatedKnowledgeSurfaceCompiler(
    GroqParallelKnowledgeSurfaceGraphCompiler
):
    """Backward-compatible import name for the production FAQ surface graph compiler."""

    def route_observability_snapshot(self) -> dict[str, object]:
        snapshot = getattr(self._client, "route_observability_snapshot", None)
        if not callable(snapshot):
            return {}
        raw_value = snapshot()
        return dict(raw_value) if isinstance(raw_value, Mapping) else {}
