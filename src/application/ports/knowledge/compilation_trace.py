from __future__ import annotations

from collections.abc import Sequence
from src.domain.project_plane.knowledge_compilation import (
    CompilationMetrics,
    CompilerBatch,
    CompilerRun,
)
from src.domain.project_plane.knowledge_views import KnowledgeCompilerBatchView
from typing import Protocol


class KnowledgeCompilationTracePort(Protocol):
    async def create_compiler_run(self, run: CompilerRun) -> None: ...

    async def complete_compiler_run(
        self,
        compiler_run_id: str,
        metrics: CompilationMetrics,
    ) -> None: ...

    async def fail_compiler_run(
        self,
        compiler_run_id: str,
        error: str,
    ) -> None: ...

    async def create_compiler_batches(
        self,
        *,
        project_id: str,
        document_id: str,
        batches: Sequence[CompilerBatch],
    ) -> int: ...

    async def mark_compiler_batch_processing(
        self,
        batch_id: str,
        *,
        attempt_count: int,
    ) -> None: ...

    async def complete_compiler_batch(
        self,
        batch_id: str,
        *,
        model: str,
        prompt_version: str,
        tokens_input: int,
        tokens_output: int,
        tokens_total: int,
    ) -> None: ...

    async def fail_compiler_batch(
        self,
        batch_id: str,
        *,
        error_type: str,
        error_message: str,
    ) -> None: ...

    async def list_document_compiler_batches(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> tuple[KnowledgeCompilerBatchView, ...]: ...
