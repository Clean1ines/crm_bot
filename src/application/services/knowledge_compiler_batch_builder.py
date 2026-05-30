from __future__ import annotations


import uuid
from collections.abc import Sequence
from src.application.services.knowledge_source_material_builder import (
    _chunk_content,
    _source_chunk_optional_int,
)
from src.domain.project_plane.json_types import JsonObject
from src.domain.project_plane.knowledge_compilation import (
    CompilationMetrics,
    CompilerBatch,
    CompilerBatchStatus,
    CompilerRun,
    CompilerRunStatus,
    SourceChunk,
)
from src.domain.project_plane.knowledge_preprocessing import KnowledgePreprocessingMode


KCD_STAGE_CD_COMPILER_VERSION = "kcd_v1_stage_cd"


KCD_STAGE_E_COMPILER_VERSION = "kcd_v1_stage_e"


KCD_STAGE_K_COMPILER_VERSION = "kcd_v1_stage_k_answer_compiler"


KCD_STAGE_K_CANCELLED_ERROR = "Knowledge preprocessing cancelled by operator"


KCD_STAGE_K_PREVIOUS_TITLE_LIMIT = 80


KCD_STAGE_K_ANSWER_DIGEST_MAX_CHARS = 220


def _source_chunk_for_technical_chunk(
    *,
    technical_chunk: JsonObject,
    source_chunks: Sequence[SourceChunk],
) -> SourceChunk | None:
    if not source_chunks:
        return None

    raw_index = _source_chunk_optional_int(technical_chunk.get("index"))
    if raw_index is not None:
        for source_chunk in source_chunks:
            if source_chunk.source_index == raw_index:
                return source_chunk

    content = _chunk_content(technical_chunk)
    if content:
        for source_chunk in source_chunks:
            if content in source_chunk.content or source_chunk.content in content:
                return source_chunk

    return None


def _compiler_batch_id(*, compiler_run_id: str, batch_index: int) -> str:
    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"{compiler_run_id}:technical-batch:{batch_index}",
        )
    )


def _compiler_batches_from_technical_batches(
    *,
    project_id: str,
    document_id: str,
    compiler_run_id: str,
    technical_batches: Sequence[Sequence[JsonObject]],
    source_chunks: Sequence[SourceChunk],
) -> tuple[CompilerBatch, ...]:
    batch_count = len(technical_batches)
    batches: list[CompilerBatch] = []

    for batch_index, technical_batch in enumerate(technical_batches, start=1):
        batch_source_chunks: list[SourceChunk] = []
        for technical_chunk in technical_batch:
            source_chunk = _source_chunk_for_technical_chunk(
                technical_chunk=technical_chunk,
                source_chunks=source_chunks,
            )
            if source_chunk is not None and source_chunk not in batch_source_chunks:
                batch_source_chunks.append(source_chunk)

        batches.append(
            CompilerBatch(
                id=_compiler_batch_id(
                    compiler_run_id=compiler_run_id,
                    batch_index=batch_index,
                ),
                project_id=project_id,
                document_id=document_id,
                compiler_run_id=compiler_run_id,
                batch_index=batch_index,
                batch_count=batch_count,
                source_chunk_ids=tuple(chunk.id for chunk in batch_source_chunks),
                source_chunk_indexes=tuple(
                    chunk.source_index for chunk in batch_source_chunks
                ),
                status=CompilerBatchStatus.PENDING,
                metadata={
                    "stage": "stage_k_technical_compiler_loop",
                    "technical_chunk_count": len(technical_batch),
                },
            )
        )

    return tuple(batches)


KCD_STAGE_K_EXTRACTION_CONCURRENCY_DEFAULT = 3


def _stage_e_compiler_run_id(
    *,
    document_id: str,
    mode: KnowledgePreprocessingMode,
) -> str:
    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"kcd_v1_stage_e:{document_id}:{mode}",
        )
    )


def _stage_e_compiler_run(
    *,
    project_id: str,
    document_id: str,
    mode: KnowledgePreprocessingMode,
    source_chunk_count: int,
) -> CompilerRun:
    return CompilerRun(
        id=_stage_e_compiler_run_id(document_id=document_id, mode=mode),
        project_id=project_id,
        document_id=document_id,
        mode=str(mode),
        compiler_version=KCD_STAGE_K_COMPILER_VERSION,
        status=CompilerRunStatus.RUNNING,
        metrics=CompilationMetrics(source_chunk_count=source_chunk_count),
    )


__all__ = [
    "KCD_STAGE_CD_COMPILER_VERSION",
    "KCD_STAGE_E_COMPILER_VERSION",
    "KCD_STAGE_K_COMPILER_VERSION",
    "KCD_STAGE_K_CANCELLED_ERROR",
    "KCD_STAGE_K_PREVIOUS_TITLE_LIMIT",
    "KCD_STAGE_K_ANSWER_DIGEST_MAX_CHARS",
    "KCD_STAGE_K_EXTRACTION_CONCURRENCY_DEFAULT",
    "_compiler_batch_id",
    "_compiler_batches_from_technical_batches",
    "_stage_e_compiler_run_id",
    "_stage_e_compiler_run",
]
