from __future__ import annotations

import re
import uuid
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Protocol, cast

from src.application.errors import ValidationError
from src.application.ports.knowledge_port import (
    KnowledgeDbPoolPort,
    KnowledgeSurfaceCompilerFactoryPort,
)
from src.application.ports.logger_port import LoggerPort
from src.application.services.knowledge_ingestion_service import (
    KnowledgeDocumentProcessingResult,
    KnowledgeIngestionRepositoryFactoryPort,
    _compiler_source_chunks_for_preprocessing,
    _indexable_chunks,
    _source_chunks_from_json_chunks,
)
from src.domain.project_plane.json_types import (
    JsonObject,
    JsonValue,
    json_value_from_unknown,
)
from src.domain.project_plane.knowledge_compilation import SourceChunk
from src.domain.project_plane.knowledge_preprocessing import (
    MODE_FAQ,
    KnowledgePreprocessingMode,
    PREPROCESSING_STATUS_COMPLETED,
    PREPROCESSING_STATUS_FAILED,
    PREPROCESSING_STATUS_PROCESSING,
    KnowledgePreprocessingValidationError,
)
from src.domain.project_plane.retrieval_surface_compilation import (
    RetrievalSurfaceCompilerRun,
    RetrievalSurfaceCompilerStage,
    RetrievalSurfaceDraft,
    RetrievalSurfaceMergeDecision,
    RetrievalSurfaceRelation,
    RetrievalSurfaceSourceChild,
    RetrievalSurfaceSourceUnit,
    SurfaceQuestionOwnership,
    SurfaceQuestionReassignment,
    SurfaceCompilerRunStatus,
    SurfaceSourceChildLabelKind,
)
from src.infrastructure.llm.knowledge_surface_compiler import (
    FAQ_RETRIEVAL_SURFACE_COMPILATION_PROMPT_VERSION,
)


FAQ_MODE: KnowledgePreprocessingMode = MODE_FAQ


class KnowledgeSurfaceIngestionRepositoryPort(Protocol):
    async def delete_document_chunks(self, document_id: str) -> None: ...

    async def add_source_chunks(
        self,
        *,
        project_id: str,
        document_id: str,
        chunks: Sequence[SourceChunk],
    ) -> int: ...

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

    async def create_surface_compiler_stage(
        self,
        stage: RetrievalSurfaceCompilerStage,
    ) -> RetrievalSurfaceCompilerStage: ...

    async def save_surface_source_units(
        self,
        *,
        run_id: str,
        document_id: str,
        source_units: tuple[RetrievalSurfaceSourceUnit, ...],
    ) -> None: ...

    async def save_surfaces(
        self,
        *,
        run_id: str,
        document_id: str,
        surfaces: tuple[RetrievalSurfaceDraft, ...],
    ) -> None: ...

    async def save_surface_relations(
        self,
        *,
        run_id: str,
        document_id: str,
        relations: tuple[RetrievalSurfaceRelation, ...],
    ) -> None: ...

    async def save_surface_question_ownership(
        self,
        *,
        run_id: str,
        document_id: str,
        ownership: tuple[SurfaceQuestionOwnership, ...],
    ) -> None: ...

    async def save_surface_question_reassignments(
        self,
        *,
        run_id: str,
        document_id: str,
        reassignments: tuple[SurfaceQuestionReassignment, ...],
    ) -> None: ...

    async def save_surface_merge_decisions(
        self,
        *,
        run_id: str,
        document_id: str,
        merge_decisions: tuple[RetrievalSurfaceMergeDecision, ...],
    ) -> None: ...

    async def update_document_preprocessing_status(
        self,
        document_id: str,
        *,
        mode: str,
        status: str,
        error: str | None = None,
        model: str | None = None,
        prompt_version: str | None = None,
        metrics: JsonObject | None = None,
    ) -> None: ...

    async def update_document_status(
        self,
        document_id: str,
        status: str,
        error: str | None = None,
    ) -> None: ...


SOURCE_CHILD_LABEL_VALUES: frozenset[str] = frozenset(
    {
        "service_label",
        "content_section",
        "question_group",
        "expected_topic",
        "short_answer",
        "negative_test",
        "other",
    }
)


def _compact_text(value: object) -> str:
    if value is None or isinstance(value, bool):
        return ""
    return " ".join(str(value).strip().split())


def _fingerprint(value: str) -> str:
    return " ".join(
        re.sub(r"[^0-9a-zа-яё]+", " ", value.lower().replace("ё", "е")).split()
    )


def _json_object(value: object) -> JsonObject:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): json_value_from_unknown(item) for key, item in value.items()}


def _json_array(value: object) -> tuple[object, ...]:
    if isinstance(value, list | tuple):
        return tuple(value)
    return ()


def _text_tuple(value: object) -> tuple[str, ...]:
    result: list[str] = []
    for item in _json_array(value):
        text = _compact_text(item)
        if text and text not in result:
            result.append(text)
    return tuple(result)


def _section_path(value: object) -> tuple[str, ...]:
    return tuple(_text_tuple(value))


def _source_unit_key(chunk: JsonObject, *, index: int) -> str:
    explicit = _compact_text(
        chunk.get("semantic_unit_id") or chunk.get("id") or chunk.get("source_unit_key")
    )
    return explicit or f"source_unit:{index}"


def _source_refs(chunk: JsonObject, *, source_index: int) -> tuple[str, ...]:
    raw_refs = chunk.get("source_refs")
    refs: list[str] = []
    if isinstance(raw_refs, list | tuple):
        for item in raw_refs:
            if isinstance(item, Mapping):
                start = _compact_text(item.get("start_offset"))
                end = _compact_text(item.get("end_offset"))
                refs.append(f"chunk:{source_index}:{start}:{end}")
                continue
            text = _compact_text(item)
            if text:
                refs.append(text)
    if refs:
        return tuple(refs)
    return (f"chunk:{source_index}",)


def _label_kind_from_title(title: str) -> SurfaceSourceChildLabelKind:
    fp = _fingerprint(title)
    if fp == "короткий ответ клиенту":
        return "short_answer"
    if fp in {"тестовые вопросы", "вопросы", "проверочные вопросы"}:
        return "question_group"
    if fp == "ожидаемая тема":
        return "expected_topic"
    if "негативн" in fp:
        return "negative_test"
    if fp in {"примечание", "служебная метка", "лейбл"}:
        return "service_label"
    return "content_section"


def _surface_source_child(item: object) -> RetrievalSurfaceSourceChild | None:
    if not isinstance(item, Mapping):
        return None
    title = _compact_text(item.get("title")) or "section"
    body = _compact_text(item.get("body") or item.get("source_excerpt"))
    raw_text = _compact_text(item.get("raw_text") or item.get("body") or body)
    if not body and not raw_text:
        return None
    return RetrievalSurfaceSourceChild(
        title=title,
        body=body or raw_text,
        raw_text=raw_text or body,
        label_kind=_label_kind_from_title(title),
        metadata=_json_object(item.get("metadata")),
    )


def _source_unit_children(chunk: JsonObject) -> tuple[RetrievalSurfaceSourceChild, ...]:
    children: list[RetrievalSurfaceSourceChild] = []
    for item in _json_array(chunk.get("children")):
        child = _surface_source_child(item)
        if child is not None:
            children.append(child)
    if children:
        return tuple(children)
    content = _compact_text(chunk.get("section_body") or chunk.get("content"))
    if not content:
        return ()
    return (
        RetrievalSurfaceSourceChild(
            title="content",
            body=content,
            raw_text=content,
            label_kind="content_section",
        ),
    )


def _source_units_from_chunks(
    *,
    run_id: str,
    document_id: str,
    chunks: Sequence[JsonObject],
) -> tuple[RetrievalSurfaceSourceUnit, ...]:
    units: list[RetrievalSurfaceSourceUnit] = []
    for index, chunk in enumerate(chunks):
        body = _compact_text(chunk.get("section_body") or chunk.get("content"))
        if not body:
            continue
        title = (
            _compact_text(
                chunk.get("section_title") or chunk.get("title") or chunk.get("id")
            )
            or f"Source unit {index + 1}"
        )
        source_index = index
        raw_index = chunk.get("index")
        if (
            isinstance(raw_index, int)
            and not isinstance(raw_index, bool)
            and raw_index >= 0
        ):
            source_index = raw_index
        source_unit_key = _source_unit_key(chunk, index=index)
        units.append(
            RetrievalSurfaceSourceUnit(
                id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{run_id}:{source_unit_key}")),
                run_id=run_id,
                document_id=document_id,
                source_unit_key=source_unit_key,
                source_chunk_indexes=(source_index,),
                title=title,
                body=body,
                children=_source_unit_children(chunk),
                raw_text=_compact_text(chunk.get("content") or body),
                section_path=_section_path(chunk.get("section_path")),
                source_refs=_source_refs(chunk, source_index=source_index),
                preprocessing_mode=FAQ_MODE,
                metadata={
                    "faq_retrieval_surface_source_unit": True,
                    "source_format": _compact_text(chunk.get("source_format")),
                    "semantic_unit_role_hint": _compact_text(
                        chunk.get("semantic_unit_role_hint")
                    ),
                },
            )
        )
    return tuple(units)


def _stage(
    *,
    run_id: str,
    document_id: str,
    stage_kind: str,
    status: SurfaceCompilerRunStatus,
    model: str,
    input_summary: str = "",
    output_summary: str = "",
    error_type: str | None = None,
    error_message: str | None = None,
    metrics: JsonObject | None = None,
) -> RetrievalSurfaceCompilerStage:
    now = datetime.now(timezone.utc)
    return RetrievalSurfaceCompilerStage(
        id=str(uuid.uuid4()),
        run_id=run_id,
        document_id=document_id,
        stage_kind=stage_kind,
        status=status,
        model=model,
        prompt_version=FAQ_RETRIEVAL_SURFACE_COMPILATION_PROMPT_VERSION,
        input_summary=input_summary,
        output_summary=output_summary,
        error_type=error_type,
        error_message=error_message,
        started_at=now,
        completed_at=now if status in {"completed", "failed", "cancelled"} else None,
        metrics=metrics or {},
    )


def _success_stage_metrics(
    *,
    source_unit_count: int,
    surface_count: int,
    relation_count: int,
    ownership_count: int,
    merge_decision_count: int,
) -> dict[str, JsonValue]:
    return {
        "source_unit_count": source_unit_count,
        "surface_count": surface_count,
        "relation_count": relation_count,
        "ownership_count": ownership_count,
        "merge_decision_count": merge_decision_count,
        "prompt_version": FAQ_RETRIEVAL_SURFACE_COMPILATION_PROMPT_VERSION,
    }


class KnowledgeFaqSurfaceIngestionService:
    def __init__(self, pool: KnowledgeDbPoolPort) -> None:
        self.pool = pool

    async def process_document(
        self,
        *,
        project_id: str,
        document_id: str,
        file_name: str,
        chunks: list[JsonObject],
        knowledge_repo_factory: KnowledgeIngestionRepositoryFactoryPort,
        surface_compiler_factory: KnowledgeSurfaceCompilerFactoryPort,
        logger: LoggerPort,
    ) -> KnowledgeDocumentProcessingResult:
        repo = cast(
            KnowledgeSurfaceIngestionRepositoryPort,
            knowledge_repo_factory(self.pool),
        )
        compiler = surface_compiler_factory()
        run_id = str(uuid.uuid4())
        await repo.delete_document_chunks(document_id)

        indexable_chunks = _indexable_chunks(chunks)
        if not indexable_chunks:
            message = "No indexable FAQ source units after filtering"
            await repo.update_document_status(document_id, "error", message)
            raise ValidationError(message)

        compiler_source_chunks = _compiler_source_chunks_for_preprocessing(
            file_name=file_name,
            chunks=indexable_chunks,
            mode=FAQ_MODE,
        )
        source_chunks = _source_chunks_from_json_chunks(
            project_id=project_id,
            document_id=document_id,
            chunks=compiler_source_chunks,
        )
        source_units = _source_units_from_chunks(
            run_id=run_id,
            document_id=document_id,
            chunks=compiler_source_chunks,
        )
        if not source_units:
            message = "FAQ surface compiler requires source units"
            await repo.update_document_status(document_id, "error", message)
            raise ValidationError(message)

        started_at = datetime.now(timezone.utc)
        await repo.create_surface_compiler_run(
            RetrievalSurfaceCompilerRun(
                id=run_id,
                project_id=project_id,
                document_id=document_id,
                mode=FAQ_MODE,
                status="running",
                compiler_kind="faq_retrieval_surface_compiler",
                model=compiler.model_name,
                prompt_version=FAQ_RETRIEVAL_SURFACE_COMPILATION_PROMPT_VERSION,
                started_at=started_at,
                metrics={
                    "source_unit_count": len(source_units),
                    "source_chunk_count": len(source_chunks),
                    "bootstrap_forbidden": True,
                },
            )
        )

        await repo.add_source_chunks(
            project_id=project_id,
            document_id=document_id,
            chunks=source_chunks,
        )
        await repo.save_surface_source_units(
            run_id=run_id,
            document_id=document_id,
            source_units=source_units,
        )
        await repo.create_surface_compiler_stage(
            _stage(
                run_id=run_id,
                document_id=document_id,
                stage_kind="source_units",
                status="completed",
                model=compiler.model_name,
                input_summary=f"chunks={len(indexable_chunks)}",
                output_summary=f"source_units={len(source_units)}",
                metrics={"source_unit_count": len(source_units)},
            )
        )
        await repo.update_document_preprocessing_status(
            document_id,
            mode=FAQ_MODE,
            status=PREPROCESSING_STATUS_PROCESSING,
            model=compiler.model_name,
            prompt_version=FAQ_RETRIEVAL_SURFACE_COMPILATION_PROMPT_VERSION,
            metrics={
                "stage": "faq_retrieval_surface_compilation",
                "status_message": "Компилируем FAQ в поисковые поверхности",
                "source_unit_count": len(source_units),
                "bootstrap_forbidden": True,
            },
        )

        try:
            result = await compiler.compile_surfaces(
                mode=FAQ_MODE,
                source_units=source_units,
                file_name=file_name,
                run_id=run_id,
            )
            graph = result.graph
            await repo.save_surfaces(
                run_id=run_id,
                document_id=document_id,
                surfaces=graph.surfaces,
            )
            await repo.save_surface_relations(
                run_id=run_id,
                document_id=document_id,
                relations=graph.relations,
            )
            await repo.save_surface_question_ownership(
                run_id=run_id,
                document_id=document_id,
                ownership=graph.ownership,
            )
            await repo.save_surface_question_reassignments(
                run_id=run_id,
                document_id=document_id,
                reassignments=graph.reassignments,
            )
            await repo.save_surface_merge_decisions(
                run_id=run_id,
                document_id=document_id,
                merge_decisions=graph.merge_decisions,
            )
        except Exception as exc:
            error_message = str(exc)[:500] or type(exc).__name__
            await repo.create_surface_compiler_stage(
                _stage(
                    run_id=run_id,
                    document_id=document_id,
                    stage_kind="faq_surface_compilation",
                    status="failed",
                    model=compiler.model_name,
                    input_summary=f"source_units={len(source_units)}",
                    error_type=type(exc).__name__,
                    error_message=error_message,
                    metrics={"bootstrap_fallback": False},
                )
            )
            await repo.update_surface_compiler_run_status(
                run_id=run_id,
                status="failed",
                error_type=type(exc).__name__,
                error_message=error_message,
            )
            await repo.update_document_preprocessing_status(
                document_id,
                mode=FAQ_MODE,
                status=PREPROCESSING_STATUS_FAILED,
                error=error_message,
                model=compiler.model_name,
                prompt_version=FAQ_RETRIEVAL_SURFACE_COMPILATION_PROMPT_VERSION,
                metrics={
                    "stage": "faq_retrieval_surface_compilation_failed",
                    "status_message": "FAQ surface compiler failed; bootstrap fallback is disabled",
                    "error_type": type(exc).__name__,
                    "bootstrap_fallback": False,
                    "surface_compiler_run_id": run_id,
                },
            )
            await repo.update_document_status(document_id, "error", error_message)
            logger.warning(
                "FAQ retrieval surface compilation failed without fallback",
                extra={
                    "project_id": project_id,
                    "document_id": document_id,
                    "error_type": type(exc).__name__,
                },
            )
            if isinstance(exc, KnowledgePreprocessingValidationError):
                raise
            raise ValidationError(error_message) from exc

        metrics = _success_stage_metrics(
            source_unit_count=len(graph.source_units),
            surface_count=len(graph.surfaces),
            relation_count=len(graph.relations),
            ownership_count=len(graph.ownership),
            merge_decision_count=len(graph.merge_decisions),
        )
        for stage_kind in (
            "surface_discovery",
            "relation_planning",
            "answer_synthesis",
            "question_ownership",
            "merge_decisions",
        ):
            await repo.create_surface_compiler_stage(
                _stage(
                    run_id=run_id,
                    document_id=document_id,
                    stage_kind=stage_kind,
                    status="completed",
                    model=result.model,
                    input_summary=f"source_units={len(graph.source_units)}",
                    output_summary=(
                        f"surfaces={len(graph.surfaces)} relations={len(graph.relations)} "
                        f"ownership={len(graph.ownership)} merges={len(graph.merge_decisions)}"
                    ),
                    metrics=metrics,
                )
            )

        await repo.update_surface_compiler_run_status(run_id=run_id, status="completed")
        preprocessing_metrics: JsonObject = {
            **result.metrics,
            "stage": "faq_retrieval_surface_compilation_completed",
            "status_message": "FAQ surfaces compiled; publish selected surfaces for runtime retrieval",
            "surface_compiler_run_id": run_id,
            "surface_count": len(graph.surfaces),
            "relation_count": len(graph.relations),
            "ownership_count": len(graph.ownership),
            "merge_decision_count": len(graph.merge_decisions),
            "source_unit_count": len(graph.source_units),
            "model": result.model,
            "prompt_version": result.prompt_version,
            "bootstrap_fallback": False,
        }
        await repo.update_document_preprocessing_status(
            document_id,
            mode=FAQ_MODE,
            status=PREPROCESSING_STATUS_COMPLETED,
            model=result.model,
            prompt_version=result.prompt_version,
            metrics=preprocessing_metrics,
        )
        await repo.update_document_status(document_id, "processed")
        logger.info(
            "FAQ retrieval surface compilation completed",
            extra={
                "project_id": project_id,
                "document_id": document_id,
                "surface_count": len(graph.surfaces),
                "ownership_count": len(graph.ownership),
            },
        )
        return KnowledgeDocumentProcessingResult(
            document_id=document_id,
            preprocessing_status=PREPROCESSING_STATUS_COMPLETED,
            structured_entries=len(graph.surfaces),
        )
