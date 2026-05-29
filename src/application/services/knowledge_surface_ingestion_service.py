from __future__ import annotations

import re
import uuid
from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import datetime, timezone
from typing import Protocol, cast, runtime_checkable

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
from src.domain.project_plane.knowledge_artifact_cleanup import (
    KnowledgeArtifactCleanupPlan,
    KnowledgeArtifactCleanupResult,
    build_document_reset_cleanup_plan,
)
from src.domain.project_plane.json_types import (
    JsonObject,
    JsonValue,
    json_value_from_unknown,
)
from src.domain.project_plane.knowledge_compilation import SourceChunk
from src.domain.project_plane.knowledge_document_lifecycle import (
    KnowledgeDocumentLifecycleDecision,
    KnowledgeDocumentLifecycleTrigger,
    TRIGGER_EXPLICIT_USER_RESUME,
    TRIGGER_NORMAL_UPLOAD,
    TRIGGER_QUOTA_RECOVERY,
    TRIGGER_STALE_JOB_RECOVERY,
    TRIGGER_WORKER_RECOVERY,
    resolve_knowledge_document_lifecycle,
)
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
from src.infrastructure.llm.knowledge_surface_graph_compiler_v2 import (
    GRAPH_PROMPT_VERSION,
)


FAQ_MODE: KnowledgePreprocessingMode = MODE_FAQ


class KnowledgeSurfaceIngestionCancelled(RuntimeError):
    """Raised when cooperative runtime cancellation stops FAQ compilation."""


@runtime_checkable
class KnowledgeSurfaceProgressAwareCompilerPort(Protocol):
    def set_progress_callback(
        self,
        callback: Callable[[Mapping[str, object]], Awaitable[None]] | None,
    ) -> None: ...


@runtime_checkable
class KnowledgeSurfaceCheckpointAwareCompilerPort(
    KnowledgeSurfaceProgressAwareCompilerPort,
    Protocol,
):
    def set_source_unit_result_checkpoints(
        self,
        checkpoints: Mapping[str, object],
    ) -> None: ...


@runtime_checkable
class KnowledgeSurfaceCancelAwareCompilerPort(Protocol):
    def set_cancel_check(
        self,
        callback: Callable[[], Awaitable[None]] | None,
    ) -> None: ...


class KnowledgeSurfaceIngestionRepositoryPort(Protocol):
    async def get_document(self, document_id: str) -> object | None: ...

    async def cleanup_document_artifacts(
        self,
        plan: KnowledgeArtifactCleanupPlan,
    ) -> KnowledgeArtifactCleanupResult: ...

    async def delete_document_chunks(self, document_id: str) -> None: ...

    async def is_document_processing_cancelled(self, document_id: str) -> bool: ...

    async def get_latest_surface_run_for_document(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> RetrievalSurfaceCompilerRun | None: ...

    async def list_surface_source_units_for_run(
        self,
        *,
        run_id: str,
    ) -> tuple[RetrievalSurfaceSourceUnit, ...]: ...

    async def list_surfaces_for_run(
        self,
        *,
        run_id: str,
    ) -> tuple[RetrievalSurfaceDraft, ...]: ...

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

    async def list_surface_stages_for_run(
        self,
        *,
        run_id: str,
    ) -> tuple[RetrievalSurfaceCompilerStage, ...]: ...

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


def _number_metric(metrics: object, key: str) -> float | None:
    if not isinstance(metrics, Mapping):
        return None
    value = metrics.get(key)
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _document_elapsed_before_resume(document: object | None) -> float:
    if document is None:
        return 0.0
    metrics = getattr(document, "preprocessing_metrics", None)
    explicit = _number_metric(metrics, "elapsed_before_resume_seconds")
    if explicit is not None and explicit > 0:
        return explicit
    elapsed = _number_metric(metrics, "elapsed_seconds")
    if elapsed is not None and elapsed > 0:
        return elapsed
    return 0.0


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


AUTO_RECOVERY_LIFECYCLE_TRIGGERS: frozenset[KnowledgeDocumentLifecycleTrigger] = (
    frozenset(
        {
            TRIGGER_WORKER_RECOVERY,
            TRIGGER_QUOTA_RECOVERY,
            TRIGGER_STALE_JOB_RECOVERY,
        }
    )
)


def _int_attr(value: object | None, name: str) -> int:
    if value is None:
        return 0
    raw_value = getattr(value, name, 0)
    if isinstance(raw_value, bool) or raw_value is None:
        return 0
    if isinstance(raw_value, int):
        return raw_value
    if isinstance(raw_value, float) and raw_value.is_integer():
        return int(raw_value)
    if isinstance(raw_value, str) and raw_value.strip().isdigit():
        return int(raw_value.strip())
    return 0


def _document_lifecycle_decision(
    document: object | None,
) -> KnowledgeDocumentLifecycleDecision:
    return resolve_knowledge_document_lifecycle(
        document_status=str(getattr(document, "status", "") or ""),
        preprocessing_status=getattr(document, "preprocessing_status", None),
        preprocessing_error=getattr(document, "preprocessing_error", None),
        preprocessing_metrics=_json_object(
            getattr(document, "preprocessing_metrics", None)
        ),
        chunk_count=_int_attr(document, "chunk_count"),
        structured_entries=_int_attr(document, "structured_entries"),
    )


def _is_reusable_faq_surface_run(
    run: RetrievalSurfaceCompilerRun | None,
) -> bool:
    return (
        run is not None
        and run.compiler_kind == "faq_retrieval_surface_compiler"
        and run.prompt_version == GRAPH_PROMPT_VERSION
        and run.status in {"running", "failed", "cancelled"}
    )


def _should_reuse_surface_run(
    *,
    latest_run: RetrievalSurfaceCompilerRun | None,
    lifecycle_trigger: KnowledgeDocumentLifecycleTrigger,
    resume_run_id: str | None,
    lifecycle_decision: KnowledgeDocumentLifecycleDecision,
) -> bool:
    if not _is_reusable_faq_surface_run(latest_run):
        return False

    assert latest_run is not None

    if lifecycle_trigger == TRIGGER_EXPLICIT_USER_RESUME:
        if not resume_run_id or resume_run_id != latest_run.id:
            return False
        return (
            latest_run.status == "cancelled"
            or latest_run.error_type == "processing_cancelled"
            or lifecycle_decision.can_manual_resume
        )

    if lifecycle_trigger in AUTO_RECOVERY_LIFECYCLE_TRIGGERS:
        if resume_run_id is not None and resume_run_id != latest_run.id:
            return False
        return (
            latest_run.status in {"failed", "running"}
            and lifecycle_decision.can_auto_resume
        )

    return False


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
        prompt_version=GRAPH_PROMPT_VERSION,
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
        "prompt_version": GRAPH_PROMPT_VERSION,
    }


def _surface_progress_message(stage_kind: str, metrics: JsonObject) -> str:
    source_unit_index = metrics.get("source_unit_index")
    source_unit_count = metrics.get("source_unit_count")
    candidate_index = metrics.get("candidate_index")
    candidate_count = metrics.get("candidate_count")
    if stage_kind == "surface_discovery":
        return f"Ищем карточки: блок {source_unit_index}/{source_unit_count}"
    if stage_kind == "relation_planning":
        return f"Строим связи: блок {source_unit_index}/{source_unit_count}"
    if stage_kind == "answer_synthesis":
        return (
            f"Пишем ответы: блок {source_unit_index}/{source_unit_count}, "
            f"карточка {candidate_index}/{candidate_count}"
        )
    if stage_kind == "question_ownership":
        return (
            f"Назначаем вопросы: блок {source_unit_index}/{source_unit_count}, "
            f"карточка {candidate_index}/{candidate_count}"
        )
    if stage_kind == "global_reconciliation":
        return "Собираем глобальный граф карточек"
    if stage_kind == "global_relation_judge":
        return "Проверяем глобальные связи и дубликаты"
    if stage_kind == "question_reassignment":
        return "Переносим вопросы между карточками"
    return "Компилируем FAQ graph"


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
        lifecycle_trigger: KnowledgeDocumentLifecycleTrigger = TRIGGER_NORMAL_UPLOAD,
        resume_run_id: str | None = None,
    ) -> KnowledgeDocumentProcessingResult:
        repo = cast(
            KnowledgeSurfaceIngestionRepositoryPort,
            knowledge_repo_factory(self.pool),
        )
        compiler = surface_compiler_factory()
        existing_document = await repo.get_document(document_id)
        latest_run = await repo.get_latest_surface_run_for_document(
            project_id=project_id,
            document_id=document_id,
        )
        lifecycle_decision = _document_lifecycle_decision(existing_document)
        resume_run = (
            latest_run
            if _should_reuse_surface_run(
                latest_run=latest_run,
                lifecycle_trigger=lifecycle_trigger,
                resume_run_id=resume_run_id,
                lifecycle_decision=lifecycle_decision,
            )
            else None
        )
        run_id = resume_run.id if resume_run is not None else str(uuid.uuid4())
        if resume_run is None:
            await repo.cleanup_document_artifacts(
                build_document_reset_cleanup_plan(
                    project_id=project_id,
                    document_id=document_id,
                )
            )

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
        existing_source_units: tuple[RetrievalSurfaceSourceUnit, ...] = ()
        if resume_run is not None:
            existing_source_units = await repo.list_surface_source_units_for_run(
                run_id=run_id,
            )
            if existing_source_units:
                source_units = existing_source_units

        if not source_units:
            message = "FAQ surface compiler requires source units"
            await repo.update_document_status(document_id, "error", message)
            raise ValidationError(message)

        started_at = datetime.now(timezone.utc)
        elapsed_before_resume = (
            _document_elapsed_before_resume(existing_document)
            if resume_run is not None
            else 0.0
        )
        processing_started_at_epoch = started_at.timestamp()
        if resume_run is None:
            await repo.create_surface_compiler_run(
                RetrievalSurfaceCompilerRun(
                    id=run_id,
                    project_id=project_id,
                    document_id=document_id,
                    mode=FAQ_MODE,
                    status="running",
                    compiler_kind="faq_retrieval_surface_compiler",
                    model=compiler.model_name,
                    prompt_version=GRAPH_PROMPT_VERSION,
                    started_at=started_at,
                    metrics={
                        "source_unit_count": len(source_units),
                        "source_chunk_count": len(source_chunks),
                        "bootstrap_forbidden": True,
                        "resume_reused_run": False,
                        "lifecycle_trigger": lifecycle_trigger,
                        "resume_run_id": resume_run_id,
                    },
                )
            )
        else:
            await repo.update_surface_compiler_run_status(
                run_id=run_id,
                status="running",
                error_type=None,
                error_message=None,
            )

        if resume_run is None or not existing_source_units:
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
                metrics={
                    "source_unit_count": len(source_units),
                    "resume_reused_run": resume_run is not None,
                    "resume_existing_source_unit_count": len(existing_source_units),
                    "lifecycle_trigger": lifecycle_trigger,
                    "resume_run_id": resume_run.id
                    if resume_run is not None
                    else resume_run_id,
                    "resume_policy": lifecycle_decision.resume_policy,
                },
            )
        )
        await repo.update_document_preprocessing_status(
            document_id,
            mode=FAQ_MODE,
            status=PREPROCESSING_STATUS_PROCESSING,
            model=compiler.model_name,
            prompt_version=GRAPH_PROMPT_VERSION,
            metrics={
                "stage": "faq_retrieval_surface_compilation",
                "status_message": "Компилируем FAQ в поисковые поверхности",
                "status": "processing",
                "source_unit_count": len(source_units),
                "bootstrap_forbidden": True,
                "resume_reused_run": resume_run is not None,
                "lifecycle_trigger": lifecycle_trigger,
                "resume_run_id": resume_run.id
                if resume_run is not None
                else resume_run_id,
                "resume_policy": lifecycle_decision.resume_policy,
                "can_auto_resume": lifecycle_decision.can_auto_resume,
                "can_manual_resume": lifecycle_decision.can_manual_resume,
                "elapsed_before_resume_seconds": round(elapsed_before_resume, 1),
                "processing_started_at_epoch": round(processing_started_at_epoch, 3),
            },
        )

        existing_surfaces = (
            await repo.list_surfaces_for_run(run_id=run_id)
            if resume_run is not None
            else ()
        )
        persisted_surface_ids: set[str] = {surface.id for surface in existing_surfaces}

        existing_unit_checkpoints: dict[str, object] = {}
        if resume_run is not None:
            for stage in await repo.list_surface_stages_for_run(run_id=run_id):
                metrics = stage.metrics
                checkpoint = metrics.get("source_unit_checkpoint")
                source_unit_key = _compact_text(
                    metrics.get("source_unit_key")
                    or (
                        checkpoint.get("source_unit_key")
                        if isinstance(checkpoint, Mapping)
                        else ""
                    )
                )
                if source_unit_key and isinstance(checkpoint, Mapping):
                    existing_unit_checkpoints[source_unit_key] = dict(checkpoint)

        if existing_unit_checkpoints and isinstance(
            compiler, KnowledgeSurfaceCheckpointAwareCompilerPort
        ):
            compiler.set_source_unit_result_checkpoints(existing_unit_checkpoints)

        cancel_stage_recorded = False

        async def ensure_not_cancelled() -> None:
            nonlocal cancel_stage_recorded
            is_cancelled = getattr(repo, "is_document_processing_cancelled", None)
            if not callable(is_cancelled):
                return
            if not await is_cancelled(document_id):
                return

            elapsed_seconds = elapsed_before_resume + max(
                0.0,
                (datetime.now(timezone.utc) - started_at).total_seconds(),
            )
            reason = "Knowledge document processing was cancelled"
            if not cancel_stage_recorded:
                cancel_stage_recorded = True
                await repo.create_surface_compiler_stage(
                    _stage(
                        run_id=run_id,
                        document_id=document_id,
                        stage_kind="faq_surface_compilation",
                        status="cancelled",
                        model=compiler.model_name,
                        input_summary=f"source_units={len(source_units)}",
                        output_summary="cancelled_before_next_llm_work",
                        error_type="processing_cancelled",
                        error_message=reason,
                        metrics={
                            "stage": "faq_retrieval_surface_compilation_cancelled",
                            "cancelled": True,
                            "surface_compiler_run_id": run_id,
                            "elapsed_seconds": round(elapsed_seconds, 1),
                            "elapsed_before_resume_seconds": round(elapsed_seconds, 1),
                        },
                    )
                )
                await repo.update_surface_compiler_run_status(
                    run_id=run_id,
                    status="cancelled",
                    error_type="processing_cancelled",
                    error_message=reason,
                )
                await repo.update_document_preprocessing_status(
                    document_id,
                    mode=FAQ_MODE,
                    status=PREPROCESSING_STATUS_FAILED,
                    error=reason,
                    model=compiler.model_name,
                    prompt_version=GRAPH_PROMPT_VERSION,
                    metrics={
                        "stage": "faq_retrieval_surface_compilation_cancelled",
                        "status": "cancelled",
                        "status_message": reason,
                        "cancelled": True,
                        "surface_compiler_run_id": run_id,
                        "elapsed_seconds": round(elapsed_seconds, 1),
                        "elapsed_before_resume_seconds": round(elapsed_seconds, 1),
                    },
                )

            raise KnowledgeSurfaceIngestionCancelled(reason)

        async def record_surface_progress(event: Mapping[str, object]) -> None:
            await ensure_not_cancelled()
            stage_kind = (
                _compact_text(event.get("stage_kind")) or "faq_surface_compilation"
            )
            raw_status = _compact_text(event.get("status")) or "running"
            status = cast(
                SurfaceCompilerRunStatus,
                raw_status
                if raw_status in {"running", "completed", "failed", "cancelled"}
                else "running",
            )
            metrics = _json_object(event.get("metrics"))
            input_summary = _compact_text(event.get("input_summary"))
            output_summary = _compact_text(event.get("output_summary"))
            error_type = _compact_text(event.get("error_type")) or None
            error_message = _compact_text(event.get("error_message")) or None
            await repo.create_surface_compiler_stage(
                _stage(
                    run_id=run_id,
                    document_id=document_id,
                    stage_kind=stage_kind,
                    status=status,
                    model=compiler.model_name,
                    input_summary=input_summary,
                    output_summary=output_summary,
                    error_type=error_type,
                    error_message=error_message,
                    metrics=metrics,
                )
            )
            raw_partial_surfaces = event.get("partial_surfaces")
            if isinstance(raw_partial_surfaces, (list, tuple)):
                partial_surfaces = tuple(
                    item
                    for item in raw_partial_surfaces
                    if isinstance(item, RetrievalSurfaceDraft)
                )
            else:
                partial_surfaces = ()
            new_partial_surfaces = tuple(
                surface
                for surface in partial_surfaces
                if surface.id not in persisted_surface_ids
            )
            if new_partial_surfaces:
                await repo.save_surfaces(
                    run_id=run_id,
                    document_id=document_id,
                    surfaces=new_partial_surfaces,
                )
                persisted_surface_ids.update(
                    surface.id for surface in new_partial_surfaces
                )
                metrics = {
                    **metrics,
                    "partial_surface_count": len(new_partial_surfaces),
                    "persisted_surface_count": len(persisted_surface_ids),
                }
            await repo.update_document_preprocessing_status(
                document_id,
                mode=FAQ_MODE,
                status=PREPROCESSING_STATUS_PROCESSING,
                model=compiler.model_name,
                prompt_version=GRAPH_PROMPT_VERSION,
                metrics={
                    **metrics,
                    "stage": stage_kind,
                    "status": status,
                    "status_message": _surface_progress_message(stage_kind, metrics),
                    "surface_compiler_run_id": run_id,
                },
            )

        if isinstance(compiler, KnowledgeSurfaceProgressAwareCompilerPort):
            compiler.set_progress_callback(record_surface_progress)

        if isinstance(compiler, KnowledgeSurfaceCancelAwareCompilerPort):
            compiler.set_cancel_check(ensure_not_cancelled)

        try:
            await ensure_not_cancelled()
            result = await compiler.compile_surfaces(
                mode=FAQ_MODE,
                source_units=source_units,
                file_name=file_name,
                run_id=run_id,
            )
            graph = result.graph
            await ensure_not_cancelled()
            final_surfaces_to_save = tuple(
                surface
                for surface in graph.surfaces
                if surface.id not in persisted_surface_ids
            )
            await repo.save_surfaces(
                run_id=run_id,
                document_id=document_id,
                surfaces=final_surfaces_to_save,
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
        except KnowledgeSurfaceIngestionCancelled as exc:
            error_message = str(exc)[:500] or type(exc).__name__
            logger.info(
                "FAQ retrieval surface compilation cancelled",
                extra={
                    "project_id": project_id,
                    "document_id": document_id,
                    "surface_compiler_run_id": run_id,
                },
            )
            return KnowledgeDocumentProcessingResult(
                document_id=document_id,
                preprocessing_status=PREPROCESSING_STATUS_FAILED,
                structured_entries=0,
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
                prompt_version=GRAPH_PROMPT_VERSION,
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
            "Knowledge document completed",
            extra={
                "project_id": project_id,
                "document_id": document_id,
                "run_id": run_id,
                "job_id": None,
                "stage_kind": "faq_retrieval_surface_compilation_completed",
                "source_unit_count": len(graph.source_units),
                "source_unit_key": None,
                "source_unit_index": None,
                "candidate_index": None,
                "requested_model": compiler.model_name,
                "actual_model": result.model,
                "key_slot": preprocessing_metrics.get("groq_key_slot_counts"),
                "limit_kind": preprocessing_metrics.get("limit_kind"),
                "fallback_reason": preprocessing_metrics.get("fallback_reason"),
                "tokens_prompt": preprocessing_metrics.get("tokens_input")
                or preprocessing_metrics.get("llm_tokens_input"),
                "tokens_completion": preprocessing_metrics.get("tokens_output")
                or preprocessing_metrics.get("llm_tokens_output"),
                "tokens_total": preprocessing_metrics.get("tokens_total")
                or preprocessing_metrics.get("llm_tokens_total"),
                "duration_ms": preprocessing_metrics.get("duration_ms"),
                "checkpoint_reused": preprocessing_metrics.get("checkpoint_reused"),
                "economy_mode": preprocessing_metrics.get("economy_mode", False),
                "total_calls": preprocessing_metrics.get("llm_call_count")
                or preprocessing_metrics.get("groq_route_event_count"),
                "total_tokens": preprocessing_metrics.get("tokens_total")
                or preprocessing_metrics.get("llm_tokens_total"),
                "models": preprocessing_metrics.get("model_counts")
                or preprocessing_metrics.get("groq_actual_model_counts")
                or result.model,
                "key_slots": preprocessing_metrics.get("groq_key_slot_counts"),
                "fallback_counts": preprocessing_metrics.get("fallback_counts"),
                "cooldown_counts": preprocessing_metrics.get(
                    "groq_route_cooldown_block_count"
                ),
                "checkpoint_reused_count": preprocessing_metrics.get(
                    "source_unit_checkpoint_reused_count",
                    preprocessing_metrics.get("checkpoint_reused_count"),
                ),
                "surface_count": len(graph.surfaces),
                "ownership_count": len(graph.ownership),
            },
        )
        return KnowledgeDocumentProcessingResult(
            document_id=document_id,
            preprocessing_status=PREPROCESSING_STATUS_COMPLETED,
            structured_entries=len(graph.surfaces),
        )
