from __future__ import annotations

from typing import Protocol

from src.domain.project_plane.retrieval_surface_compilation import (
    RetrievalSurfaceCompilerStage,
    SurfaceCompilerRunStatus,
)


class KnowledgeSurfaceCompilerStagePort(Protocol):
    async def create_surface_compiler_stage(
        self,
        stage: RetrievalSurfaceCompilerStage,
    ) -> RetrievalSurfaceCompilerStage: ...

    async def update_surface_compiler_stage_status(
        self,
        *,
        stage_id: str,
        status: SurfaceCompilerRunStatus,
        error_type: str | None = None,
        error_message: str | None = None,
    ) -> None: ...

    async def list_surface_stages_for_run(
        self,
        *,
        run_id: str,
    ) -> tuple[RetrievalSurfaceCompilerStage, ...]: ...
