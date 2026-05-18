from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from enum import Enum
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.application.errors import ConflictError
from src.application.services.knowledge_curation_service import KnowledgeCurationService
from src.application.services.project_service import ProjectAccessService
from src.domain.project_plane.json_types import json_object_from_unknown
from src.domain.project_plane.knowledge_compilation import (
    KnowledgeEntryStatus,
    KnowledgeEntryVisibility,
)
from src.domain.project_plane.knowledge_curation import (
    KnowledgeCurationActionType,
    KnowledgeEntryMergeExcludeOptions,
    KnowledgeEntryMergeIncludeOptions,
    KnowledgeEntryMergeRequest,
    KnowledgeEntryPatch,
    KnowledgeEntryStatusTransition,
)
from src.infrastructure.db.repositories.knowledge_repository import KnowledgeRepository
from src.infrastructure.db.repositories.queue_repository import QueueRepository
from src.interfaces.http.dependencies import (
    get_current_user_id,
    get_pool,
    get_project_service,
    get_queue_repo,
)

router = APIRouter(
    prefix="/api/projects/{project_id}/knowledge/{document_id}/curation",
    tags=["knowledge-curation"],
)


class QueueAdapter:
    def __init__(self, queue: QueueRepository) -> None:
        self.queue = queue

    async def enqueue_task(self, task_type: str, payload: Mapping[str, object]) -> str:
        return await self.queue.enqueue(
            task_type, json_object_from_unknown(dict(payload))
        )


def _serialize(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return {key: _serialize(item) for key, item in asdict(value).items()}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _serialize(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_serialize(item) for item in value]
    if hasattr(value, "isoformat"):
        return str(value.isoformat())
    return value


def _service(
    pool: object, queue_repo: QueueRepository | None = None
) -> KnowledgeCurationService:
    queue = QueueAdapter(queue_repo) if queue_repo is not None else None
    return KnowledgeCurationService(KnowledgeRepository(pool), queue)


async def _require_read_access(
    project_id: str, user_id: str, project_service: ProjectAccessService
) -> None:
    await project_service.require_project_role(
        project_id, user_id, ["owner", "admin", "manager"]
    )


async def _require_mutation_access(
    project_id: str, user_id: str, project_service: ProjectAccessService
) -> None:
    await project_service.require_project_role(project_id, user_id, ["owner", "admin"])


def _handle_value_error(exc: ValueError) -> None:
    message = str(exc)
    if (
        "version_conflict" in message
        or "source refs" in message
        or "already applied" in message
        or "cross-document" in message
    ):
        raise HTTPException(
            status_code=409, detail={"code": message, "message": message}
        ) from exc
    if "not found" in message:
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": message}
        ) from exc
    raise HTTPException(
        status_code=400, detail={"code": "invalid_request", "message": message}
    ) from exc


class KnowledgeCurationStatusRequest(BaseModel):
    action: KnowledgeCurationActionType
    target_status: KnowledgeEntryStatus | None = None
    target_visibility: KnowledgeEntryVisibility | None = None
    expected_version: int | None = Field(default=None, ge=1)
    reason: str = Field(default="", max_length=1000)
    rebuild_embedding: bool = False
    rerun_eval: bool = False
    idempotency_key: str = Field(default="", max_length=200)


class KnowledgeEntryPatchRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    answer: str | None = Field(default=None, min_length=1, max_length=8000)
    enrichment: dict[str, object] | None = None
    source_refs: list[dict[str, object]] | None = None
    expected_version: int | None = Field(default=None, ge=1)
    reason: str = Field(default="", max_length=1000)
    rebuild_embedding: bool = False
    rerun_eval: bool = False
    idempotency_key: str = Field(default="", max_length=200)


class KnowledgeEntryMergeIncludeRequest(BaseModel):
    answers: bool = True
    questions: bool = True
    paraphrases: bool = True
    synonyms: bool = True
    typo_queries: bool = True
    colloquial_queries: bool = True
    tags: bool = True
    retrieval_guards: bool = False
    source_refs: bool = True
    metadata: bool = True


class KnowledgeEntryMergeExcludeRequest(BaseModel):
    question_values: list[str] = Field(default_factory=list)
    synonym_values: list[str] = Field(default_factory=list)
    tag_values: list[str] = Field(default_factory=list)
    source_ref_keys: list[str] = Field(default_factory=list)
    metadata_keys: list[str] = Field(default_factory=list)


class KnowledgeEntryMergeRequestModel(BaseModel):
    parent_entry_id: str = Field(min_length=1)
    absorbed_entry_ids: list[str] = Field(min_length=1, max_length=11)
    parent_expected_version: int | None = Field(default=None, ge=1)
    absorbed_expected_versions: dict[str, int] = Field(default_factory=dict)
    merge_instruction: str = Field(default="", max_length=2000)
    final_title: str | None = Field(default=None, min_length=1, max_length=300)
    final_answer: str | None = Field(default=None, min_length=1, max_length=8000)
    include: KnowledgeEntryMergeIncludeRequest = Field(
        default_factory=KnowledgeEntryMergeIncludeRequest
    )
    exclude: KnowledgeEntryMergeExcludeRequest = Field(
        default_factory=KnowledgeEntryMergeExcludeRequest
    )
    absorbed_status: str = "merged"
    rebuild_embedding: bool = True
    rerun_eval: bool = False
    idempotency_key: str = Field(min_length=1, max_length=200)


def _merge_request(
    payload: KnowledgeEntryMergeRequestModel,
) -> KnowledgeEntryMergeRequest:
    return KnowledgeEntryMergeRequest(
        parent_entry_id=payload.parent_entry_id,
        absorbed_entry_ids=tuple(payload.absorbed_entry_ids),
        parent_expected_version=payload.parent_expected_version,
        absorbed_expected_versions=payload.absorbed_expected_versions,
        merge_instruction=payload.merge_instruction,
        final_title=payload.final_title,
        final_answer=payload.final_answer,
        include=KnowledgeEntryMergeIncludeOptions(**payload.include.model_dump()),
        exclude=KnowledgeEntryMergeExcludeOptions(
            question_values=tuple(payload.exclude.question_values),
            synonym_values=tuple(payload.exclude.synonym_values),
            tag_values=tuple(payload.exclude.tag_values),
            source_ref_keys=tuple(payload.exclude.source_ref_keys),
            metadata_keys=tuple(payload.exclude.metadata_keys),
        ),
        absorbed_status=payload.absorbed_status,
        rebuild_embedding=payload.rebuild_embedding,
        rerun_eval=payload.rerun_eval,
        idempotency_key=payload.idempotency_key,
    )


@router.get("")
async def get_document_curation(
    project_id: str,
    document_id: str,
    current_user_id: Annotated[str, Depends(get_current_user_id)],
    pool: Annotated[object, Depends(get_pool)],
    project_service: Annotated[ProjectAccessService, Depends(get_project_service)],
):
    await _require_read_access(project_id, current_user_id, project_service)
    result = await _service(pool).load_document_curation_state(
        project_id=project_id, document_id=document_id
    )
    return _serialize(result)


@router.post("/entries/{entry_id}/status")
async def set_entry_status(
    project_id: str,
    document_id: str,
    entry_id: str,
    request: KnowledgeCurationStatusRequest,
    current_user_id: Annotated[str, Depends(get_current_user_id)],
    pool: Annotated[object, Depends(get_pool)],
    project_service: Annotated[ProjectAccessService, Depends(get_project_service)],
):
    await _require_mutation_access(project_id, current_user_id, project_service)
    try:
        entry = await _service(pool).apply_status_transition(
            project_id=project_id,
            document_id=document_id,
            entry_id=entry_id,
            actor_user_id=current_user_id,
            transition=KnowledgeEntryStatusTransition(**request.model_dump()),
        )
    except ValueError as exc:
        _handle_value_error(exc)
    return {"ok": True, "entry": _serialize(entry)}


@router.patch("/entries/{entry_id}")
async def patch_entry(
    project_id: str,
    document_id: str,
    entry_id: str,
    request: KnowledgeEntryPatchRequest,
    current_user_id: Annotated[str, Depends(get_current_user_id)],
    pool: Annotated[object, Depends(get_pool)],
    project_service: Annotated[ProjectAccessService, Depends(get_project_service)],
):
    await _require_mutation_access(project_id, current_user_id, project_service)
    patch = KnowledgeEntryPatch(
        title=request.title,
        answer=request.answer,
        enrichment=request.enrichment,
        source_refs=tuple(request.source_refs or ())
        if request.source_refs is not None
        else None,
        expected_version=request.expected_version,
        reason=request.reason,
        rebuild_embedding=request.rebuild_embedding,
        rerun_eval=request.rerun_eval,
        idempotency_key=request.idempotency_key,
    )
    try:
        entry = await _service(pool).patch_entry(
            project_id=project_id,
            document_id=document_id,
            entry_id=entry_id,
            actor_user_id=current_user_id,
            patch=patch,
        )
    except ValueError as exc:
        _handle_value_error(exc)
    return {"ok": True, "entry": _serialize(entry)}


@router.post("/entries/{entry_id}/embedding/rebuild")
async def rebuild_entry_embedding(
    project_id: str,
    document_id: str,
    entry_id: str,
    current_user_id: Annotated[str, Depends(get_current_user_id)],
    pool: Annotated[object, Depends(get_pool)],
    project_service: Annotated[ProjectAccessService, Depends(get_project_service)],
):
    await _require_mutation_access(project_id, current_user_id, project_service)
    try:
        result = await _service(pool).rebuild_embedding(
            project_id=project_id,
            document_id=document_id,
            entry_id=entry_id,
            action_id=f"manual_embedding_rebuild:{entry_id}",
        )
    except ValueError as exc:
        _handle_value_error(exc)
    return result


@router.post("/merge/preview")
async def preview_merge(
    project_id: str,
    document_id: str,
    request: KnowledgeEntryMergeRequestModel,
    current_user_id: Annotated[str, Depends(get_current_user_id)],
    pool: Annotated[object, Depends(get_pool)],
    project_service: Annotated[ProjectAccessService, Depends(get_project_service)],
):
    await _require_read_access(project_id, current_user_id, project_service)
    preview = await _service(pool).build_merge_preview(
        project_id=project_id, document_id=document_id, request=_merge_request(request)
    )
    return {"ok": not bool(preview.blocking_errors), "preview": _serialize(preview)}


@router.post("/merge/apply")
async def apply_merge(
    project_id: str,
    document_id: str,
    request: KnowledgeEntryMergeRequestModel,
    current_user_id: Annotated[str, Depends(get_current_user_id)],
    pool: Annotated[object, Depends(get_pool)],
    queue_repo: Annotated[QueueRepository, Depends(get_queue_repo)],
    project_service: Annotated[ProjectAccessService, Depends(get_project_service)],
):
    await _require_mutation_access(project_id, current_user_id, project_service)
    service = _service(pool, queue_repo)
    try:
        result = await service.apply_merge(
            project_id=project_id,
            document_id=document_id,
            actor_user_id=current_user_id,
            request=_merge_request(request),
        )
        job_id = await service.enqueue_rerun_eval_if_requested(
            project_id=project_id,
            document_id=document_id,
            actor_user_id=current_user_id,
            enabled=request.rerun_eval,
        )
    except ValueError as exc:
        _handle_value_error(exc)
    except ConflictError as exc:
        raise HTTPException(
            status_code=409, detail={"code": "merge_conflict", "message": exc.detail}
        ) from exc
    payload = _serialize(result)
    if isinstance(payload, dict) and job_id:
        payload["rerun_eval_job_id"] = job_id
    return payload


@router.get("/actions")
async def list_actions(
    project_id: str,
    document_id: str,
    current_user_id: Annotated[str, Depends(get_current_user_id)],
    pool: Annotated[object, Depends(get_pool)],
    project_service: Annotated[ProjectAccessService, Depends(get_project_service)],
    limit: int = Query(100, ge=1, le=200),
):
    await _require_read_access(project_id, current_user_id, project_service)
    actions = await _service(pool).list_actions(
        project_id=project_id, document_id=document_id, limit=limit
    )
    return {"ok": True, "actions": _serialize(actions)}


@router.get("/entries/{entry_id}/versions")
async def list_versions(
    project_id: str,
    document_id: str,
    entry_id: str,
    current_user_id: Annotated[str, Depends(get_current_user_id)],
    pool: Annotated[object, Depends(get_pool)],
    project_service: Annotated[ProjectAccessService, Depends(get_project_service)],
):
    await _require_read_access(project_id, current_user_id, project_service)
    versions = await _service(pool).list_versions(
        project_id=project_id, document_id=document_id, entry_id=entry_id
    )
    return {"ok": True, "versions": _serialize(versions)}


class RestoreVersionRequest(BaseModel):
    reason: str = Field(default="", max_length=1000)


@router.post("/entries/{entry_id}/versions/{version_id}/restore")
async def restore_version(
    project_id: str,
    document_id: str,
    entry_id: str,
    version_id: str,
    request: RestoreVersionRequest,
    current_user_id: Annotated[str, Depends(get_current_user_id)],
    pool: Annotated[object, Depends(get_pool)],
    project_service: Annotated[ProjectAccessService, Depends(get_project_service)],
):
    await _require_mutation_access(project_id, current_user_id, project_service)
    try:
        entry = await _service(pool).restore_version(
            project_id=project_id,
            document_id=document_id,
            entry_id=entry_id,
            version_id=version_id,
            actor_user_id=current_user_id,
            reason=request.reason,
        )
    except ValueError as exc:
        _handle_value_error(exc)
    return {"ok": True, "entry": _serialize(entry)}
