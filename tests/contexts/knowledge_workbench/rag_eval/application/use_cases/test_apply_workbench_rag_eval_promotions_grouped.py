from __future__ import annotations

import asyncio
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone

import pytest

from src.contexts.embedding_runtime.application.ports.embedding_generation_port import (
    EmbeddingGenerationRequest,
    EmbeddingGenerationResult,
)
from src.contexts.knowledge_workbench.rag_eval.application.errors.workbench_rag_eval_promotion_application_errors import (
    WorkbenchRagEvalPromotionConflictCode,
    WorkbenchRagEvalPromotionConflictError,
)
from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval import (
    WorkbenchRagEvalPromotionApplicationTarget,
    WorkbenchRagEvalPromotionStatus,
)
from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval_embedding_revision import (
    WORKBENCH_RUNTIME_EMBEDDING_DIMENSIONS,
    WorkbenchRagEvalEmbeddingRevision,
    WorkbenchRagEvalEmbeddingRevisionReadModel,
    WorkbenchRagEvalPromotionApplicationCandidate,
    WorkbenchRagEvalPromotionApplicationClaim,
    WorkbenchRagEvalPromotionApplicationClaimDecision,
    WorkbenchRagEvalPromotionApplicationClaimDecisionCode,
    WorkbenchRagEvalPromotionApplicationClaimStatus,
    WorkbenchRagEvalPromotionApplicationSnapshot,
    stable_promotion_application_key,
    stable_runtime_snapshot_hash,
)
from src.contexts.knowledge_workbench.rag_eval.application.policies.promoted_question_runtime_embedding_text_builder import (
    PromotedQuestionRuntimeEmbeddingTextBuilder,
)
from src.contexts.knowledge_workbench.rag_eval.application.policies.workbench_rag_eval_promotion_application_policy import (
    WorkbenchRagEvalPromotionApplicationPolicy,
)
from src.contexts.knowledge_workbench.rag_eval.application.use_cases.apply_workbench_rag_eval_promotions_batch import (
    ApplyWorkbenchRagEvalPromotionsBatch,
)


NOW = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)
VECTOR_384 = (0.0,) * WORKBENCH_RUNTIME_EMBEDDING_DIMENSIONS
NEW_VECTOR_384 = (0.5,) * WORKBENCH_RUNTIME_EMBEDDING_DIMENSIONS


def _target(
    promotion_id: str = "promotion-1",
    *,
    status: WorkbenchRagEvalPromotionStatus = WorkbenchRagEvalPromotionStatus.APPROVED,
) -> WorkbenchRagEvalPromotionApplicationTarget:
    return WorkbenchRagEvalPromotionApplicationTarget(
        promotion_id=promotion_id,
        run_id="run-1",
        question_id=f"question-{promotion_id}",
        project_id="project-1",
        target_runtime_entry_id="entry-1",
        target_fact_id="fact-1",
        question="New alias?",
        status=status,
        claim="Claim text",
        runtime_possible_questions=("Existing?",),
        fact_possible_questions=("Existing?",),
        exclusion_scope=None,
        existing_embedding_text=(
            "Claim:\nClaim text\n\nPossible questions:\n- Existing?"
        ),
    )


def _snapshot(
    target: WorkbenchRagEvalPromotionApplicationTarget,
) -> WorkbenchRagEvalPromotionApplicationSnapshot:
    candidates = (
        WorkbenchRagEvalPromotionApplicationCandidate(
            promotion_id=target.promotion_id,
            run_id=target.run_id,
            question_id=target.question_id,
            target_fact_id=target.target_fact_id,
            question=target.question,
            status=target.status,
        ),
    )
    return WorkbenchRagEvalPromotionApplicationSnapshot(
        project_id=target.project_id,
        runtime_entry_id=target.target_runtime_entry_id,
        fact_id=target.target_fact_id,
        runtime_status="active",
        runtime_visibility="published",
        claim=target.claim,
        possible_questions=target.runtime_possible_questions,
        active_promoted_questions=(),
        exclusion_scope=target.exclusion_scope,
        embedding_text=target.existing_embedding_text,
        embedding=VECTOR_384,
        embedding_model_id="model-1",
        embedding_dimensions=WORKBENCH_RUNTIME_EMBEDDING_DIMENSIONS,
        candidates=candidates,
        runtime_hash=stable_runtime_snapshot_hash(
            possible_questions=target.runtime_possible_questions,
            embedding_text=target.existing_embedding_text,
            embedding=VECTOR_384,
            embedding_model_id="model-1",
            embedding_dimensions=WORKBENCH_RUNTIME_EMBEDDING_DIMENSIONS,
        ),
        active_revision_id=None,
    )


def _read_model(
    revision: WorkbenchRagEvalEmbeddingRevision,
) -> WorkbenchRagEvalEmbeddingRevisionReadModel:
    return WorkbenchRagEvalEmbeddingRevisionReadModel(
        revision_id=revision.revision_id,
        project_id=revision.project_id,
        runtime_entry_id=revision.runtime_entry_id,
        source_rag_eval_run_id=revision.source_rag_eval_run_id,
        promotion_ids=revision.promotion_ids,
        status=revision.status,
        previous_promoted_questions=revision.previous_promoted_questions,
        new_promoted_questions=revision.new_promoted_questions,
        created_at=revision.created_at,
        accepted_at=revision.accepted_at,
        regression_failed_at=revision.regression_failed_at,
        rolled_back_at=revision.rolled_back_at,
    )


@dataclass(slots=True)
class SharedPersistedClaimRepository:
    target: WorkbenchRagEvalPromotionApplicationTarget = field(default_factory=_target)
    claim: WorkbenchRagEvalPromotionApplicationClaim | None = None
    revisions: dict[str, WorkbenchRagEvalEmbeddingRevisionReadModel] = field(
        default_factory=dict
    )
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    snapshot_load_count: int = 0
    both_snapshots_loaded: asyncio.Event = field(default_factory=asyncio.Event)
    second_claim_attempted: asyncio.Event = field(default_factory=asyncio.Event)
    runtime_mutation_count: int = 0
    persist_count: int = 0
    fail_persistence: bool = False
    require_two_initial_snapshots: bool = False

    async def list_promotion_application_targets_for_ids(
        self,
        *,
        project_id: str,
        promotion_ids,
    ):
        assert project_id == "project-1"
        return (self.target,) if self.target.promotion_id in promotion_ids else ()

    async def list_promotion_application_targets_for_run(
        self,
        *,
        project_id: str,
        run_id: str,
    ):
        assert project_id == "project-1"
        return (self.target,) if self.target.run_id == run_id else ()

    async def load_promotion_application_group(
        self,
        *,
        project_id: str,
        promotion_ids,
        target_runtime_entry_id: str,
        embedding_model_id: str,
    ):
        assert project_id == "project-1"
        assert target_runtime_entry_id == "entry-1"
        assert embedding_model_id == "model-1"
        snapshot = _snapshot(self.target)
        self.snapshot_load_count += 1
        if self.require_two_initial_snapshots and not self.revisions:
            if self.snapshot_load_count >= 2:
                self.both_snapshots_loaded.set()
            else:
                await self.both_snapshots_loaded.wait()
        return snapshot

    async def claim_promotion_application(
        self,
        *,
        application_key: str,
        project_id: str,
        runtime_entry_id: str,
        source_rag_eval_run_id: str,
        promotion_ids,
        previous_runtime_hash: str,
        lease_owner: str,
        now: datetime,
        lease_expires_at: datetime,
    ) -> WorkbenchRagEvalPromotionApplicationClaimDecision:
        async with self.lock:
            if self.claim is None:
                self.claim = WorkbenchRagEvalPromotionApplicationClaim(
                    application_key=application_key,
                    project_id=project_id,
                    runtime_entry_id=runtime_entry_id,
                    source_rag_eval_run_id=source_rag_eval_run_id,
                    promotion_ids=tuple(promotion_ids),
                    previous_runtime_hash=previous_runtime_hash,
                    status=WorkbenchRagEvalPromotionApplicationClaimStatus.PREPARING,
                    lease_owner=lease_owner,
                    lease_expires_at=lease_expires_at,
                    revision_id=None,
                    created_at=now,
                    updated_at=now,
                    completed_at=None,
                )
                return WorkbenchRagEvalPromotionApplicationClaimDecision(
                    code=WorkbenchRagEvalPromotionApplicationClaimDecisionCode.ACQUIRED,
                    claim=self.claim,
                )
            if self.claim.application_key != application_key:
                return WorkbenchRagEvalPromotionApplicationClaimDecision(
                    code=(
                        WorkbenchRagEvalPromotionApplicationClaimDecisionCode.CONFLICTING_ACTIVE_GROUP
                    ),
                    claim=self.claim,
                )
            if (
                self.claim.status
                is WorkbenchRagEvalPromotionApplicationClaimStatus.COMPLETED
            ):
                assert self.claim.revision_id is not None
                return WorkbenchRagEvalPromotionApplicationClaimDecision(
                    code=(
                        WorkbenchRagEvalPromotionApplicationClaimDecisionCode.ALREADY_COMPLETED
                    ),
                    claim=self.claim,
                    revision=self.revisions[self.claim.revision_id],
                )
            if (
                self.claim.status
                is WorkbenchRagEvalPromotionApplicationClaimStatus.PREPARING
                and self.claim.lease_expires_at > now
            ):
                self.second_claim_attempted.set()
                return WorkbenchRagEvalPromotionApplicationClaimDecision(
                    code=(
                        WorkbenchRagEvalPromotionApplicationClaimDecisionCode.IN_PROGRESS
                    ),
                    claim=self.claim,
                )
            recovered_code = (
                WorkbenchRagEvalPromotionApplicationClaimDecisionCode.RECOVERED_EXPIRED_LEASE
                if self.claim.status
                is WorkbenchRagEvalPromotionApplicationClaimStatus.PREPARING
                else WorkbenchRagEvalPromotionApplicationClaimDecisionCode.ACQUIRED
            )
            self.claim = replace(
                self.claim,
                status=WorkbenchRagEvalPromotionApplicationClaimStatus.PREPARING,
                lease_owner=lease_owner,
                lease_expires_at=lease_expires_at,
                revision_id=None,
                updated_at=now,
                completed_at=None,
            )
            return WorkbenchRagEvalPromotionApplicationClaimDecision(
                code=recovered_code,
                claim=self.claim,
            )

    async def complete_promotion_application_claim(
        self,
        *,
        application_key: str,
        lease_owner: str,
        revision_id: str,
        completed_at: datetime,
    ) -> None:
        async with self.lock:
            if (
                self.claim is not None
                and self.claim.application_key == application_key
                and self.claim.status
                is WorkbenchRagEvalPromotionApplicationClaimStatus.COMPLETED
                and self.claim.revision_id == revision_id
            ):
                return
            if (
                self.claim is None
                or self.claim.application_key != application_key
                or self.claim.lease_owner != lease_owner
                or self.claim.status
                is not WorkbenchRagEvalPromotionApplicationClaimStatus.PREPARING
            ):
                raise WorkbenchRagEvalPromotionConflictError(
                    "lease lost",
                    code=WorkbenchRagEvalPromotionConflictCode.APPLICATION_LEASE_LOST,
                )
            self.claim = replace(
                self.claim,
                status=WorkbenchRagEvalPromotionApplicationClaimStatus.COMPLETED,
                revision_id=revision_id,
                updated_at=completed_at,
                completed_at=completed_at,
            )

    async def fail_promotion_application_claim(
        self,
        *,
        application_key: str,
        lease_owner: str,
        failed_at: datetime,
    ) -> None:
        async with self.lock:
            if (
                self.claim is None
                or self.claim.application_key != application_key
                or self.claim.lease_owner != lease_owner
                or self.claim.status
                is not WorkbenchRagEvalPromotionApplicationClaimStatus.PREPARING
            ):
                raise WorkbenchRagEvalPromotionConflictError(
                    "lease lost",
                    code=WorkbenchRagEvalPromotionConflictCode.APPLICATION_LEASE_LOST,
                )
            self.claim = replace(
                self.claim,
                status=WorkbenchRagEvalPromotionApplicationClaimStatus.FAILED,
                lease_expires_at=failed_at,
                updated_at=failed_at,
            )

    async def persist_promotion_application_revision(
        self,
        *,
        snapshot: WorkbenchRagEvalPromotionApplicationSnapshot,
        revision: WorkbenchRagEvalEmbeddingRevision,
        application_key: str,
        lease_owner: str,
    ) -> WorkbenchRagEvalEmbeddingRevisionReadModel:
        async with self.lock:
            assert self.claim is not None
            if (
                self.claim.application_key != application_key
                or self.claim.lease_owner != lease_owner
                or self.claim.status
                is not WorkbenchRagEvalPromotionApplicationClaimStatus.PREPARING
            ):
                raise WorkbenchRagEvalPromotionConflictError(
                    "lease lost",
                    code=WorkbenchRagEvalPromotionConflictCode.APPLICATION_LEASE_LOST,
                )
            if self.fail_persistence:
                raise WorkbenchRagEvalPromotionConflictError(
                    "injected persistence failure",
                    code=WorkbenchRagEvalPromotionConflictCode.PERSISTENCE_CONFLICT,
                )
            read_model = _read_model(revision)
            self.revisions[revision.revision_id] = read_model
            self.persist_count += 1
            self.runtime_mutation_count += 1
            self.target = replace(
                self.target,
                status=WorkbenchRagEvalPromotionStatus.APPLIED,
            )
            self.claim = replace(
                self.claim,
                status=WorkbenchRagEvalPromotionApplicationClaimStatus.COMPLETED,
                revision_id=revision.revision_id,
                updated_at=revision.created_at,
                completed_at=revision.created_at,
            )
            return read_model

    async def find_pending_revision_for_promotions(
        self,
        *,
        project_id: str,
        runtime_entry_id: str,
        source_rag_eval_run_id: str,
        promotion_ids,
    ):
        requested = tuple(sorted(promotion_ids))
        for revision in self.revisions.values():
            if (
                revision.project_id == project_id
                and revision.runtime_entry_id == runtime_entry_id
                and revision.source_rag_eval_run_id == source_rag_eval_run_id
                and tuple(sorted(revision.promotion_ids)) == requested
            ):
                return revision
        return None


@dataclass(slots=True)
class BarrierEmbeddingPort:
    repository: SharedPersistedClaimRepository
    calls: list[EmbeddingGenerationRequest] = field(default_factory=list)
    wait_for_second_claim: bool = True
    mutation_count_at_first_call: int | None = None

    async def embed(
        self,
        request: EmbeddingGenerationRequest,
    ) -> EmbeddingGenerationResult:
        self.calls.append(request)
        if self.mutation_count_at_first_call is None:
            self.mutation_count_at_first_call = self.repository.runtime_mutation_count
        if self.wait_for_second_claim:
            await asyncio.wait_for(
                self.repository.second_claim_attempted.wait(),
                timeout=1,
            )
        return EmbeddingGenerationResult(
            embeddings=(NEW_VECTOR_384,),
            model_id=request.model_id,
            dimensions=WORKBENCH_RUNTIME_EMBEDDING_DIMENSIONS,
        )


def _service(
    repository: SharedPersistedClaimRepository,
    embedding: BarrierEmbeddingPort,
    owners: list[str],
) -> ApplyWorkbenchRagEvalPromotionsBatch:
    def next_owner() -> str:
        return owners.pop(0)

    return ApplyWorkbenchRagEvalPromotionsBatch(
        rag_eval_repository=repository,
        embedding_generation_port=embedding,
        embedding_model_id="model-1",
        embedding_dimensions=WORKBENCH_RUNTIME_EMBEDDING_DIMENSIONS,
        embedding_text_builder=PromotedQuestionRuntimeEmbeddingTextBuilder(),
        application_policy=WorkbenchRagEvalPromotionApplicationPolicy(),
        application_lease_seconds=300,
        lease_owner_factory=next_owner,
    )


@pytest.mark.asyncio
async def test_two_simultaneous_same_group_applications_call_provider_once() -> None:
    repository = SharedPersistedClaimRepository(
        require_two_initial_snapshots=True,
    )
    embedding = BarrierEmbeddingPort(repository=repository)
    service = _service(repository, embedding, ["owner-1", "owner-2"])

    first, second = await asyncio.gather(
        service.execute(
            project_id="project-1",
            mode="selected",
            promotion_ids=("promotion-1",),
            run_id=None,
            applied_at=NOW,
        ),
        service.execute(
            project_id="project-1",
            mode="selected",
            promotion_ids=("promotion-1",),
            run_id=None,
            applied_at=NOW,
        ),
    )

    results = (first, second)
    assert len(embedding.calls) == 1
    assert embedding.mutation_count_at_first_call == 0
    assert repository.persist_count == 1
    assert repository.runtime_mutation_count == 1
    assert len(repository.revisions) == 1
    assert sum(result.applied_count for result in results) == 1
    assert any(
        error.code
        == WorkbenchRagEvalPromotionConflictCode.APPLICATION_IN_PROGRESS.value
        for result in results
        for error in result.errors
    )


@pytest.mark.asyncio
async def test_completed_claim_returns_idempotent_revision_without_embedding() -> None:
    repository = SharedPersistedClaimRepository()
    first_embedding = BarrierEmbeddingPort(
        repository=repository,
        wait_for_second_claim=False,
    )
    first_service = _service(repository, first_embedding, ["owner-1"])
    first = await first_service.execute(
        project_id="project-1",
        mode="selected",
        promotion_ids=("promotion-1",),
        run_id=None,
        applied_at=NOW,
    )
    assert first.applied_count == 1
    repository.target = replace(
        repository.target,
        status=WorkbenchRagEvalPromotionStatus.APPROVED,
    )

    second_embedding = BarrierEmbeddingPort(
        repository=repository,
        wait_for_second_claim=False,
    )
    second_service = _service(repository, second_embedding, ["owner-2"])
    second = await second_service.execute(
        project_id="project-1",
        mode="selected",
        promotion_ids=("promotion-1",),
        run_id=None,
        applied_at=NOW + timedelta(seconds=1),
    )

    assert second.revisions[0].idempotent is True
    assert second.embedding_recalculation_count == 0
    assert second_embedding.calls == []
    assert repository.persist_count == 1


@pytest.mark.asyncio
async def test_expired_lease_is_recovered_and_stale_owner_cannot_complete() -> None:
    repository = SharedPersistedClaimRepository()
    snapshot = _snapshot(repository.target)
    repository.claim = WorkbenchRagEvalPromotionApplicationClaim(
        application_key=stable_promotion_application_key(
            project_id="project-1",
            runtime_entry_id="entry-1",
            source_rag_eval_run_id="run-1",
            promotion_ids=("promotion-1",),
            previous_runtime_hash=snapshot.runtime_hash,
        ),
        project_id="project-1",
        runtime_entry_id="entry-1",
        source_rag_eval_run_id="run-1",
        promotion_ids=("promotion-1",),
        previous_runtime_hash=snapshot.runtime_hash,
        status=WorkbenchRagEvalPromotionApplicationClaimStatus.PREPARING,
        lease_owner="stale-owner",
        lease_expires_at=NOW - timedelta(seconds=1),
        revision_id=None,
        created_at=NOW - timedelta(minutes=10),
        updated_at=NOW - timedelta(minutes=10),
        completed_at=None,
    )

    application_key = repository.claim.application_key
    embedding = BarrierEmbeddingPort(
        repository=repository,
        wait_for_second_claim=False,
    )
    service = _service(repository, embedding, ["recovered-owner"])
    result = await service.execute(
        project_id="project-1",
        mode="selected",
        promotion_ids=("promotion-1",),
        run_id=None,
        applied_at=NOW,
    )

    assert result.applied_count == 1
    assert len(embedding.calls) == 1
    assert repository.persist_count == 1
    assert repository.runtime_mutation_count == 1
    assert repository.claim is not None
    assert repository.claim.status is (
        WorkbenchRagEvalPromotionApplicationClaimStatus.COMPLETED
    )
    assert repository.claim.lease_owner == "recovered-owner"

    with pytest.raises(WorkbenchRagEvalPromotionConflictError) as exc_info:
        await repository.complete_promotion_application_claim(
            application_key=application_key,
            lease_owner="stale-owner",
            revision_id="revision-stale",
            completed_at=NOW,
        )
    assert exc_info.value.code is (
        WorkbenchRagEvalPromotionConflictCode.APPLICATION_LEASE_LOST
    )


@pytest.mark.asyncio
async def test_persistence_failure_marks_claim_failed_after_rollback() -> None:
    repository = SharedPersistedClaimRepository(fail_persistence=True)
    embedding = BarrierEmbeddingPort(
        repository=repository,
        wait_for_second_claim=False,
    )
    service = _service(repository, embedding, ["owner-1"])

    result = await service.execute(
        project_id="project-1",
        mode="selected",
        promotion_ids=("promotion-1",),
        run_id=None,
        applied_at=NOW,
    )

    assert repository.runtime_mutation_count == 0
    assert repository.persist_count == 0
    assert repository.claim is not None
    assert repository.claim.status is (
        WorkbenchRagEvalPromotionApplicationClaimStatus.FAILED
    )
    assert result.errors[0].code == (
        WorkbenchRagEvalPromotionConflictCode.PERSISTENCE_CONFLICT.value
    )


@dataclass(slots=True)
class FailingEmbeddingPort:
    calls: int = 0

    async def embed(
        self,
        request: EmbeddingGenerationRequest,
    ) -> EmbeddingGenerationResult:
        del request
        self.calls += 1
        raise RuntimeError("provider unavailable")


@pytest.mark.asyncio
async def test_provider_failure_marks_claim_failed_without_runtime_mutation() -> None:
    repository = SharedPersistedClaimRepository()
    embedding = FailingEmbeddingPort()
    service = ApplyWorkbenchRagEvalPromotionsBatch(
        rag_eval_repository=repository,
        embedding_generation_port=embedding,
        embedding_model_id="model-1",
        embedding_dimensions=WORKBENCH_RUNTIME_EMBEDDING_DIMENSIONS,
        embedding_text_builder=PromotedQuestionRuntimeEmbeddingTextBuilder(),
        application_policy=WorkbenchRagEvalPromotionApplicationPolicy(),
        application_lease_seconds=300,
        lease_owner_factory=lambda: "owner-1",
    )

    result = await service.execute(
        project_id="project-1",
        mode="selected",
        promotion_ids=("promotion-1",),
        run_id=None,
        applied_at=NOW,
    )

    assert embedding.calls == 1
    assert repository.persist_count == 0
    assert repository.runtime_mutation_count == 0
    assert repository.revisions == {}
    assert repository.claim is not None
    assert repository.claim.status is (
        WorkbenchRagEvalPromotionApplicationClaimStatus.FAILED
    )
    assert result.errors[0].code == "embedding_failed"
