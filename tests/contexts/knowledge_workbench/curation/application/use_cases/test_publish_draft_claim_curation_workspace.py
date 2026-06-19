from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_prompt_contract import (
    DraftClaimCompactionMergeDecision,
    DraftClaimCompactionTriplePredicate,
)
from src.contexts.embedding_runtime.application.ports.embedding_generation_port import (
    EmbeddingGenerationRequest,
    EmbeddingGenerationResult,
)
from src.contexts.knowledge_workbench.curation.application.models.draft_claim_curation_publication import (
    DraftClaimCurationPublicationCandidate,
    DraftClaimCurationPublicationResult,
)
from src.contexts.knowledge_workbench.curation.application.models.draft_claim_curation_workspace import (
    DraftClaimCurationItemEditablePayload,
    DraftClaimCurationWorkspace,
    DraftClaimCurationWorkspaceItem,
    DraftClaimCurationWorkspaceSnapshot,
    DraftClaimCurationWorkspaceStatus,
)
from src.contexts.knowledge_workbench.curation.application.use_cases.publish_draft_claim_curation_workspace import (
    DraftClaimCurationPublicationEmbeddingError,
    DraftClaimCurationPublicationEmptyError,
    PublishDraftClaimCurationWorkspace,
)


def _now() -> datetime:
    return datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)


def _valid_predicate() -> str:
    return next(iter(DraftClaimCompactionTriplePredicate)).value


def _valid_merge_decision() -> str:
    return next(iter(DraftClaimCompactionMergeDecision)).value


def _payload(claim: str) -> dict[str, object]:
    return {
        "key": "claim-key",
        "claim": claim,
        "claim_kind": "definition",
        "granularity": "atomic",
        "source_claim_refs": ["raw-1"],
        "triples": [
            {
                "subject": "A",
                "predicate": _valid_predicate(),
                "object": "B",
                "qualifiers": [],
            }
        ],
        "merge_decision": _valid_merge_decision(),
        "possible_questions": ["What is B?"],
        "exclusion_scope": "",
        "evidence_block": "Evidence",
    }


def _item(*, excluded: bool = False) -> DraftClaimCurationWorkspaceItem:
    original = DraftClaimCurationItemEditablePayload.from_payload(
        _payload("Original claim")
    )
    editable = DraftClaimCurationItemEditablePayload.from_payload(
        _payload("Edited claim")
    )
    return DraftClaimCurationWorkspaceItem(
        item_ref="item-1",
        workspace_ref="workspace-1",
        workflow_run_id="workflow-1",
        group_ref="group-1",
        compacted_node_ref="compacted-1",
        source_claim_refs=("raw-1",),
        original_payload=original,
        editable_payload=editable,
        excluded=excluded,
        exclusion_reason="skip" if excluded else None,
        created_at=_now(),
        updated_at=_now(),
    )


def _snapshot(
    *,
    items: tuple[DraftClaimCurationWorkspaceItem, ...],
    status: DraftClaimCurationWorkspaceStatus = DraftClaimCurationWorkspaceStatus.DRAFT,
) -> DraftClaimCurationWorkspaceSnapshot:
    return DraftClaimCurationWorkspaceSnapshot(
        workspace=DraftClaimCurationWorkspace(
            workspace_ref="workspace-1",
            workflow_run_id="workflow-1",
            project_id="11111111-1111-1111-1111-111111111111",
            source_document_ref="source-document:project-1:abc",
            status=status,
            created_at=_now(),
            updated_at=_now(),
        ),
        items=items,
    )


@dataclass(slots=True)
class FakeWorkspaceRepository:
    snapshot: DraftClaimCurationWorkspaceSnapshot | None

    async def get_workspace_by_workflow_run_id(
        self,
        *,
        workflow_run_id: str,
    ) -> DraftClaimCurationWorkspaceSnapshot | None:
        assert workflow_run_id == "workflow-1"
        return self.snapshot


@dataclass(slots=True)
class FakePublicationRepository:
    candidate: DraftClaimCurationPublicationCandidate | None = None

    async def publish_curated_claims(
        self,
        *,
        publication: DraftClaimCurationPublicationCandidate,
    ) -> DraftClaimCurationPublicationResult:
        self.candidate = publication
        return DraftClaimCurationPublicationResult(
            status="published",
            publication_id=publication.publication_id,
            workflow_run_id=publication.workflow_run_id,
            project_id=publication.project_id,
            source_document_ref=publication.source_document_ref,
            published_item_count=len(publication.items),
            excluded_item_count=publication.excluded_item_count,
            runtime_entry_count=len(publication.items),
            embedding_count=len(publication.items),
            deleted_draft_embedding_count=3,
            automatic_processing_elapsed_seconds=None,
            published_at=publication.published_at,
        )


@dataclass(slots=True)
class FakeEmbeddingPort:
    requests: list[EmbeddingGenerationRequest] = field(default_factory=list)
    dimensions: int = 384
    extra_embedding: bool = False

    async def embed(
        self,
        request: EmbeddingGenerationRequest,
    ) -> EmbeddingGenerationResult:
        self.requests.append(request)
        vectors = tuple(
            tuple(0.1 for _ in range(self.dimensions)) for _ in request.texts
        )
        if self.extra_embedding:
            vectors = vectors + (tuple(0.2 for _ in range(self.dimensions)),)
        return EmbeddingGenerationResult(
            embeddings=vectors,
            model_id=request.model_id,
            dimensions=self.dimensions,
        )


@pytest.mark.asyncio
async def test_publish_uses_editable_payload_not_original_payload() -> None:
    publication_repo = FakePublicationRepository()
    embedding_port = FakeEmbeddingPort()

    result = await PublishDraftClaimCurationWorkspace(
        curation_workspace_repository=FakeWorkspaceRepository(
            snapshot=_snapshot(items=(_item(),))
        ),
        curation_publication_repository=publication_repo,
        embedding_generation_port=embedding_port,
        embedding_model_id="test-model",
        embedding_dimensions=384,
    ).execute(workflow_run_id="workflow-1", published_at=_now())

    assert result.status == "published"
    assert publication_repo.candidate is not None
    published_item = publication_repo.candidate.items[0]
    assert published_item.claim == "Edited claim"
    assert "Edited claim" in published_item.embedding_text
    assert "Original claim" not in published_item.embedding_text
    assert embedding_port.requests[0].texts == (published_item.embedding_text,)


@pytest.mark.asyncio
async def test_publish_skips_excluded_items() -> None:
    publication_repo = FakePublicationRepository()

    result = await PublishDraftClaimCurationWorkspace(
        curation_workspace_repository=FakeWorkspaceRepository(
            snapshot=_snapshot(items=(_item(), _item(excluded=True)))
        ),
        curation_publication_repository=publication_repo,
        embedding_generation_port=FakeEmbeddingPort(),
        embedding_model_id="test-model",
        embedding_dimensions=384,
    ).execute(workflow_run_id="workflow-1", published_at=_now())

    assert result.published_item_count == 1
    assert result.excluded_item_count == 1


@pytest.mark.asyncio
async def test_publish_replay_returns_existing_result_without_reembedding() -> None:
    embedding_port = FakeEmbeddingPort()
    publication_repo = FakePublicationRepository()

    result = await PublishDraftClaimCurationWorkspace(
        curation_workspace_repository=FakeWorkspaceRepository(
            snapshot=_snapshot(
                items=(_item(), _item(excluded=True)),
                status=DraftClaimCurationWorkspaceStatus.PUBLISHED,
            )
        ),
        curation_publication_repository=publication_repo,
        embedding_generation_port=embedding_port,
        embedding_model_id="test-model",
        embedding_dimensions=384,
    ).execute(workflow_run_id="workflow-1", published_at=_now())

    assert result.publication_id == "draft-claim-curation-publication:workflow-1"
    assert result.published_item_count == 1
    assert result.excluded_item_count == 1
    assert embedding_port.requests == []
    assert publication_repo.candidate is None


@pytest.mark.asyncio
async def test_publish_empty_workspace_raises() -> None:
    with pytest.raises(DraftClaimCurationPublicationEmptyError):
        await PublishDraftClaimCurationWorkspace(
            curation_workspace_repository=FakeWorkspaceRepository(
                snapshot=_snapshot(items=(_item(excluded=True),))
            ),
            curation_publication_repository=FakePublicationRepository(),
            embedding_generation_port=FakeEmbeddingPort(),
            embedding_model_id="test-model",
            embedding_dimensions=384,
        ).execute(workflow_run_id="workflow-1", published_at=_now())


@pytest.mark.asyncio
async def test_embedding_count_mismatch_raises() -> None:
    with pytest.raises(DraftClaimCurationPublicationEmbeddingError):
        await PublishDraftClaimCurationWorkspace(
            curation_workspace_repository=FakeWorkspaceRepository(
                snapshot=_snapshot(items=(_item(),))
            ),
            curation_publication_repository=FakePublicationRepository(),
            embedding_generation_port=FakeEmbeddingPort(extra_embedding=True),
            embedding_model_id="test-model",
            embedding_dimensions=384,
        ).execute(workflow_run_id="workflow-1", published_at=_now())
