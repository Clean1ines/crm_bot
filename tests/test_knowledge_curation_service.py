from __future__ import annotations

from dataclasses import dataclass, field, replace

import pytest

from src.application.errors import ConflictError, ValidationError
from src.application.services.knowledge_curation_service import KnowledgeCurationService
from src.domain.project_plane.knowledge_compilation import (
    KnowledgeEntryKind,
    KnowledgeEntryStatus,
    KnowledgeEntryVisibility,
)
from src.domain.project_plane.knowledge_curation import (
    KnowledgeCurationActionType,
    KnowledgeCurationEntryView,
    KnowledgeEntryMergeApplyResult,
    KnowledgeEntryMergePreview,
    KnowledgeEntryMergeRequest,
    KnowledgeEntryPatch,
    KnowledgeEntryStatusTransition,
)


def entry(
    entry_id: str,
    *,
    title: str = "Title",
    answer: str = "Useful grounded answer",
    status: KnowledgeEntryStatus = KnowledgeEntryStatus.NEEDS_REVIEW,
    visibility: KnowledgeEntryVisibility = KnowledgeEntryVisibility.OWNER_ONLY,
    version: int = 1,
    source_refs: tuple[dict[str, object], ...] = (
        {"quote": "quote", "source_chunk_id": "chunk", "source_index": 0},
    ),
    enrichment: dict[str, object] | None = None,
    metadata: dict[str, object] | None = None,
    has_retrieval_surface: bool = False,
    has_embedding: bool = True,
) -> KnowledgeCurationEntryView:
    return KnowledgeCurationEntryView(
        id=entry_id,
        project_id="project",
        document_id="document",
        stable_key=f"stable-{entry_id}",
        entry_kind=KnowledgeEntryKind.ANSWER,
        title=title,
        answer=answer,
        status=status,
        visibility=visibility,
        version=version,
        enrichment=enrichment or {"questions": ["How to buy?"], "tags": ["sales"]},
        source_refs=source_refs,
        metadata=metadata or {},
        has_retrieval_surface=has_retrieval_surface,
        has_embedding=has_embedding,
        runtime_eligible=status == KnowledgeEntryStatus.PUBLISHED
        and visibility == KnowledgeEntryVisibility.RUNTIME
        and bool(source_refs),
    )


@dataclass
class FakeQueue:
    calls: list[dict[str, object]] = field(default_factory=list)

    async def enqueue_task(self, task_type: str, payload: dict[str, object]) -> str:
        self.calls.append({"task_type": task_type, "payload": payload})
        return "job-1"


@dataclass
class FakeKnowledgeCurationRepository:
    entries: dict[str, KnowledgeCurationEntryView] = field(default_factory=dict)
    status_calls: list[dict[str, object]] = field(default_factory=list)
    patch_calls: list[dict[str, object]] = field(default_factory=list)
    merge_preview_calls: list[KnowledgeEntryMergeRequest] = field(default_factory=list)
    merge_apply_calls: list[dict[str, object]] = field(default_factory=list)
    rebuild_action_calls: list[dict[str, object]] = field(default_factory=list)
    rebuild_calls: list[dict[str, object]] = field(default_factory=list)
    merge_preview: KnowledgeEntryMergePreview | None = None
    merge_apply_result: KnowledgeEntryMergeApplyResult | None = None

    async def get_document_for_curation(
        self, *, project_id: str, document_id: str
    ) -> dict[str, object]:
        return {
            "id": document_id,
            "project_id": project_id,
            "file_name": "doc.md",
            "status": "completed",
            "processing_stage": "completed",
            "preprocessing_status": "completed",
            "chunk_count": len(self.entries),
            "canonical_entry_count": len(self.entries),
            "retrieval_surface_count": 0,
            "legacy_chunk_count": 0,
            "created_at": None,
            "updated_at": None,
        }

    async def list_document_canonical_entries(
        self, *, project_id: str, document_id: str
    ) -> tuple[KnowledgeCurationEntryView, ...]:
        return tuple(self.entries.values())

    async def update_entry_status_visibility(
        self,
        *,
        project_id: str,
        document_id: str,
        entry_id: str,
        action_type: str,
        actor_user_id: str,
        expected_version: int | None,
        status: str,
        visibility: str,
        reason: str,
        idempotency_key: str,
        rebuild_embedding: bool = False,
    ) -> KnowledgeCurationEntryView:
        self.status_calls.append(
            {
                "entry_id": entry_id,
                "action_type": action_type,
                "status": status,
                "visibility": visibility,
                "expected_version": expected_version,
                "reason": reason,
                "idempotency_key": idempotency_key,
                "rebuild_embedding": rebuild_embedding,
            }
        )
        current = self.entries[entry_id]
        updated = replace(
            current,
            status=KnowledgeEntryStatus(status),
            visibility=KnowledgeEntryVisibility(visibility),
            version=current.version + 1,
        )
        self.entries[entry_id] = updated
        return updated

    async def update_entry_content(
        self,
        *,
        project_id: str,
        document_id: str,
        entry_id: str,
        actor_user_id: str,
        patch: KnowledgeEntryPatch,
    ) -> KnowledgeCurationEntryView:
        self.patch_calls.append({"entry_id": entry_id, "patch": patch})
        current = self.entries[entry_id]
        updated = replace(
            current,
            title=patch.title or current.title,
            answer=patch.answer or current.answer,
            enrichment=patch.enrichment or current.enrichment,
            version=current.version + 1,
        )
        self.entries[entry_id] = updated
        return updated

    async def preview_manual_entry_merge(
        self,
        *,
        project_id: str,
        document_id: str,
        request: KnowledgeEntryMergeRequest,
    ) -> KnowledgeEntryMergePreview:
        self.merge_preview_calls.append(request)
        if self.merge_preview is None:
            raise AssertionError("merge_preview was not configured")
        return self.merge_preview

    async def apply_manual_entry_merge(
        self,
        *,
        project_id: str,
        document_id: str,
        actor_user_id: str,
        request: KnowledgeEntryMergeRequest,
        preview: KnowledgeEntryMergePreview,
    ) -> KnowledgeEntryMergeApplyResult:
        self.merge_apply_calls.append({"request": request, "preview": preview})
        if self.merge_apply_result is not None:
            return self.merge_apply_result
        return KnowledgeEntryMergeApplyResult(
            ok=True,
            partial=False,
            action_id="action",
            parent_entry_id=request.parent_entry_id,
            absorbed_entry_ids=request.absorbed_entry_ids,
            parent_version=2,
            embedding_rebuilt=False,
            rerun_eval_enqueued=False,
            preview=preview,
        )

    async def create_manual_rebuild_embedding_action(
        self,
        *,
        project_id: str,
        document_id: str,
        entry_id: str,
        actor_user_id: str,
        expected_version: int | None,
        reason: str,
        idempotency_key: str,
    ) -> str:
        self.rebuild_action_calls.append(
            {
                "entry_id": entry_id,
                "actor_user_id": actor_user_id,
                "expected_version": expected_version,
                "reason": reason,
                "idempotency_key": idempotency_key,
            }
        )
        return "rebuild-action"

    async def rebuild_entry_embedding(
        self,
        *,
        action_id: str,
        project_id: str,
        document_id: str,
        target_entry_id: str,
    ) -> None:
        self.rebuild_calls.append(
            {
                "action_id": action_id,
                "target_entry_id": target_entry_id,
            }
        )


@pytest.mark.asyncio
async def test_status_transition_delegates_status_visibility_and_rerun() -> None:
    repo = FakeKnowledgeCurationRepository(entries={"e1": entry("e1")})
    queue = FakeQueue()
    service = KnowledgeCurationService(repository=repo, queue=queue)

    result = await service.apply_status_transition(
        project_id="project",
        document_id="document",
        entry_id="e1",
        actor_user_id="actor",
        transition=KnowledgeEntryStatusTransition(
            action=KnowledgeCurationActionType.HIDE_ENTRY,
            expected_version=1,
            reason="hide noise",
            rebuild_embedding=False,
            rerun_eval=True,
            idempotency_key="status-key",
        ),
    )

    assert result.status == KnowledgeEntryStatus.HIDDEN
    assert repo.status_calls == [
        {
            "entry_id": "e1",
            "action_type": "hide_entry",
            "status": "hidden",
            "visibility": "hidden",
            "expected_version": 1,
            "reason": "hide noise",
            "idempotency_key": "status-key",
            "rebuild_embedding": False,
        }
    ]
    assert queue.calls == [
        {
            "task_type": "run_full_rag_eval",
            "payload": {
                "project_id": "project",
                "document_id": "document",
                "requested_by": "actor",
                "source": "knowledge_curation_console",
            },
        }
    ]


@pytest.mark.asyncio
async def test_patch_rejects_blank_title_and_answer() -> None:
    repo = FakeKnowledgeCurationRepository(entries={"e1": entry("e1")})
    service = KnowledgeCurationService(repository=repo)

    with pytest.raises(ValidationError):
        await service.patch_entry(
            project_id="project",
            document_id="document",
            entry_id="e1",
            actor_user_id="actor",
            patch=KnowledgeEntryPatch(
                title="  ",
                expected_version=1,
                idempotency_key="patch-key",
            ),
        )

    with pytest.raises(ValidationError):
        await service.patch_entry(
            project_id="project",
            document_id="document",
            entry_id="e1",
            actor_user_id="actor",
            patch=KnowledgeEntryPatch(
                answer="  ",
                expected_version=1,
                idempotency_key="patch-key-2",
            ),
        )

    assert repo.patch_calls == []


@pytest.mark.asyncio
async def test_patch_delegates_and_enqueues_rerun() -> None:
    repo = FakeKnowledgeCurationRepository(entries={"e1": entry("e1")})
    queue = FakeQueue()
    service = KnowledgeCurationService(repository=repo, queue=queue)

    updated = await service.patch_entry(
        project_id="project",
        document_id="document",
        entry_id="e1",
        actor_user_id="actor",
        patch=KnowledgeEntryPatch(
            title="New title",
            answer="New answer",
            expected_version=1,
            reason="fix",
            rebuild_embedding=False,
            rerun_eval=True,
            idempotency_key="patch-key",
        ),
    )

    assert updated.title == "New title"
    assert updated.answer == "New answer"
    assert len(repo.patch_calls) == 1
    assert queue.calls == [
        {
            "task_type": "run_full_rag_eval",
            "payload": {
                "project_id": "project",
                "document_id": "document",
                "requested_by": "actor",
                "source": "knowledge_curation_console",
            },
        }
    ]


@pytest.mark.asyncio
async def test_rebuild_embedding_creates_action_before_rebuild() -> None:
    repo = FakeKnowledgeCurationRepository(entries={"e1": entry("e1")})
    service = KnowledgeCurationService(repository=repo)

    result = await service.rebuild_embedding(
        project_id="project",
        document_id="document",
        entry_id="e1",
        actor_user_id="actor",
        expected_version=1,
        reason="refresh vector",
        idempotency_key="rebuild-key",
    )

    assert result == {"ok": True, "entry_id": "e1", "action_id": "rebuild-action"}
    assert repo.rebuild_action_calls == [
        {
            "entry_id": "e1",
            "actor_user_id": "actor",
            "expected_version": 1,
            "reason": "refresh vector",
            "idempotency_key": "rebuild-key",
        }
    ]
    assert repo.rebuild_calls == [
        {"action_id": "rebuild-action", "target_entry_id": "e1"}
    ]


@pytest.mark.asyncio
async def test_apply_merge_refuses_blocking_preview() -> None:
    repo = FakeKnowledgeCurationRepository(
        entries={
            "parent": entry("parent", status=KnowledgeEntryStatus.REJECTED),
            "child": entry("child"),
        }
    )
    service = KnowledgeCurationService(repository=repo)
    request = KnowledgeEntryMergeRequest(
        parent_entry_id="parent",
        absorbed_entry_ids=("child",),
        idempotency_key="",
    )

    with pytest.raises(ConflictError):
        await service.apply_merge(
            project_id="project",
            document_id="document",
            actor_user_id="actor",
            request=request,
        )

    assert repo.merge_apply_calls == []


@pytest.mark.asyncio
async def test_apply_merge_delegates_after_clean_preview() -> None:
    repo = FakeKnowledgeCurationRepository(
        entries={
            "parent": entry("parent"),
            "child": entry("child"),
        }
    )
    service = KnowledgeCurationService(repository=repo)
    request = KnowledgeEntryMergeRequest(
        parent_entry_id="parent",
        absorbed_entry_ids=("child",),
        idempotency_key="merge-key",
    )
    repo.merge_preview = service._build_merge_preview_from_entries(
        request=request,
        by_id={
            "parent": entry("parent"),
            "child": entry("child"),
        },
    )

    result = await service.apply_merge(
        project_id="project",
        document_id="document",
        actor_user_id="actor",
        request=request,
    )

    assert result.ok is True
    assert result.action_id == "action"
    assert len(repo.merge_apply_calls) == 1


@pytest.mark.asyncio
async def test_apply_merge_returns_idempotent_replay_even_when_current_preview_blocks() -> (
    None
):
    repo = FakeKnowledgeCurationRepository(
        entries={
            "parent": entry("parent"),
            "child": entry(
                "child",
                status=KnowledgeEntryStatus.MERGED,
                visibility=KnowledgeEntryVisibility.HIDDEN,
                metadata={"curation": {"merged_into": "parent"}},
            ),
        }
    )
    service = KnowledgeCurationService(repository=repo)
    request = KnowledgeEntryMergeRequest(
        parent_entry_id="parent",
        absorbed_entry_ids=("child",),
        idempotency_key="merge-key",
    )
    replay_preview = service._build_merge_preview_from_entries(
        request=request,
        by_id=repo.entries,
    )
    repo.merge_apply_result = KnowledgeEntryMergeApplyResult(
        ok=True,
        partial=False,
        action_id="action",
        parent_entry_id="parent",
        absorbed_entry_ids=("child",),
        parent_version=2,
        embedding_rebuilt=True,
        rerun_eval_enqueued=False,
        preview=replay_preview,
        replayed=True,
    )

    result = await service.apply_merge(
        project_id="project",
        document_id="document",
        actor_user_id="actor",
        request=request,
    )

    assert result.replayed is True
    assert result.action_id == "action"
    assert len(repo.merge_apply_calls) == 1
