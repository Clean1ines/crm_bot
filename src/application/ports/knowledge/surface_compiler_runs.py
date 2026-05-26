from __future__ import annotations

from typing import Protocol

from src.domain.project_plane.retrieval_surface_compilation import (
    RetrievalSurfaceCompilerRun,
    SurfaceCompilerRunStatus,
)


class KnowledgeSurfaceCompilerRunPort(Protocol):
    async def create_surface_compiler_run(
        self,
        run: RetrievalSurfaceCompilerRun,
    ) -> RetrievalSurfaceCompilerRun: ...

    async def update_surface_compiler_run_status(
        self,
        *,
        run_id: str,
        status: SurfaceCompilerRunStatus,
        error_type: str | None = None,
        error_message: str | None = None,
    ) -> None: ...

    async def get_latest_surface_run_for_document(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> RetrievalSurfaceCompilerRun | None: ...

    async def list_surface_runs_for_document(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> tuple[RetrievalSurfaceCompilerRun, ...]: ...

    async def mark_previous_surface_runs_superseded_if_needed(
        self,
        *,
        project_id: str,
        document_id: str,
        latest_run_id: str,
    ) -> None: ...
