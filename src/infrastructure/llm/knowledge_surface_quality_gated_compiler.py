from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import replace

from src.domain.project_plane.json_types import JsonObject, json_value_from_unknown
from src.domain.project_plane.knowledge_preprocessing import KnowledgePreprocessingMode
from src.domain.project_plane.retrieval_surface_compilation import (
    RetrievalSurfaceCompilationResult,
    RetrievalSurfaceSourceUnit,
)
from src.infrastructure.llm.knowledge_surface_compiler import ProgressCallback
from src.infrastructure.llm.knowledge_surface_economy_instant import (
    GroqEconomyInstantKnowledgeSurfaceGraphCompiler,
)


SurfaceProgressCallback = Callable[[Mapping[str, object]], Awaitable[None]]


class GroqQualityGatedKnowledgeSurfaceCompiler(
    GroqEconomyInstantKnowledgeSurfaceGraphCompiler
):
    """Backward-compatible import name for the production FAQ surface graph compiler."""

    def route_observability_snapshot(self) -> dict[str, object]:
        snapshot = getattr(self._client, "route_observability_snapshot", None)
        if not callable(snapshot):
            return {}
        raw_value = snapshot()
        return dict(raw_value) if isinstance(raw_value, Mapping) else {}

    def _route_metrics(self) -> JsonObject:
        return {
            str(key): json_value_from_unknown(value)
            for key, value in self.route_observability_snapshot().items()
        }

    def set_progress_callback(
        self,
        callback: ProgressCallback | None,
    ) -> None:
        if callback is None:
            super().set_progress_callback(None)
            return

        async def callback_with_route_metrics(event: Mapping[str, object]) -> None:
            raw_metrics = event.get("metrics")
            metrics = dict(raw_metrics) if isinstance(raw_metrics, Mapping) else {}
            result = callback(
                {
                    **dict(event),
                    "metrics": {
                        **metrics,
                        **self._route_metrics(),
                    },
                }
            )
            if result is not None:
                await result

        super().set_progress_callback(callback_with_route_metrics)

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
        route_metrics = self._route_metrics()
        if not route_metrics:
            return result

        graph = replace(
            result.graph,
            metrics={
                **result.graph.metrics,
                **route_metrics,
            },
        )
        return replace(
            result,
            graph=graph,
            metrics={
                **result.metrics,
                **route_metrics,
            },
        )
