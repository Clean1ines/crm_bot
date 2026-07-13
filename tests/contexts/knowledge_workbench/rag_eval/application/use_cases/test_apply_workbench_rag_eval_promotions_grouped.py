from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone

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
    WorkbenchRagEvalEmbeddingRevision,
    WorkbenchRagEvalEmbeddingRevisionReadModel,
    WorkbenchRagEvalEmbeddingRevisionStatus,
    WorkbenchRagEvalPromotionApplicationCandidate,
    WorkbenchRagEvalPromotionApplicationSnapshot,
    stable_runtime_snapshot_hash,
)
from src.contexts.knowledge_workbench.rag_eval.application.policies.promoted_question_runtime_embedding_text_builder import (
    PromotedQuestionRuntimeEmbeddingTextBuilder,
)
from src.contexts.knowledge_workbench.rag_eval.application.policies.workbench_rag_eval_promotion_application_policy import (
    WorkbenchRagEvalPromotionApplicationPolicy,
    WorkbenchRagEvalPromotionApplicationPolicyConfig,
)
from src.contexts.knowledge_workbench.rag_eval.application.use_cases.apply_workbench_rag_eval_promotion import (
    ApplyWorkbenchRagEvalPromotion,
)
from src.contexts.knowledge_workbench.rag_eval.application.use_cases.apply_workbench_rag_eval_promotions_batch import (
    ApplyWorkbenchRagEvalPromotionsBatch,
)


NOW = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)


def _target(
    promotion_id: str,
    *,
    runtime_entry_id: str = "entry-1",
    run_id: str = "run-1",
    question: str = "New alias?",
    status: WorkbenchRagEvalPromotionStatus = WorkbenchRagEvalPromotionStatus.APPROVED,
) -> WorkbenchRagEvalPromotionApplicationTarget:
    return WorkbenchRagEvalPromotionApplicationTarget(
        promotion_id=promotion_id,
        run_id=run_id,
        question_id=f"question-{promotion_id}",
        project_id="project-1",
        target_runtime_entry_id=runtime_entry_id,
        target_fact_id=f"fact-{runtime_entry_id}",
        question=question,
        status=status,
        claim=f"Claim {runtime_entry_id}",
        runtime_possible_questions=("Existing?",),
        fact_possible_questions=("Existing?",),
        exclusion_scope=None,
        existing_embedding_text=(
            f"Claim:\nClaim {runtime_entry_id}\n\n"
            "Possible questions:\n- Existing?\n\nEvidence:\nEvidence"
        ),
    )


def _snapshot(
    targets: tuple[WorkbenchRagEvalPromotionApplicationTarget, ...],
    *,
    active_revision_id: str | None = None,
) -> WorkbenchRagEvalPromotionApplicationSnapshot:
    first = targets[0]
    embedding = (0.1, 0.2, 0.3)
    candidates = tuple(
        WorkbenchRagEvalPromotionApplicationCandidate(
            promotion_id=target.promotion_id,
            run_id=target.run_id,
            question_id=target.question_id,
            target_fact_id=target.target_fact_id,
            question=target.question,
            status=target.status,
        )
        for target in targets
    )
    return WorkbenchRagEvalPromotionApplicationSnapshot(
        project_id=first.project_id,
        runtime_entry_id=first.target_runtime_entry_id,
        fact_id=first.target_fact_id,
        runtime_status="active",
        runtime_visibility="published",
        claim=first.claim,
        possible_questions=first.runtime_possible_questions,
        exclusion_scope=first.exclusion_scope,
        embedding_text=first.existing_embedding_text,
        embedding=embedding,
        embedding_model_id="model-1",
        embedding_dimensions=3,
        candidates=candidates,
        runtime_hash=stable_runtime_snapshot_hash(
            possible_questions=first.runtime_possible_questions,
            embedding_text=first.existing_embedding_text,
            embedding=embedding,
            embedding_model_id="model-1",
            embedding_dimensions=3,
        ),
        active_revision_id=active_revision_id,
    )


@dataclass(slots=True)
class FakeEmbeddingPort:
    calls: list[EmbeddingGenerationRequest] = field(default_factory=list)
    fail_for_text: str | None = None

    async def embed(
        self,
        request: EmbeddingGenerationRequest,
    ) -> EmbeddingGenerationResult:
        self.calls.append(request)
        if self.fail_for_text and self.fail_for_text in request.texts[0]:
            raise RuntimeError("embedding failed")
        return EmbeddingGenerationResult(
            embeddings=((0.4, 0.5, 0.6),),
            model_id=request.model_id,
            dimensions=request.expected_dimensions,
        )


@dataclass(slots=True)
class FakeRepository:
    targets: list[WorkbenchRagEvalPromotionApplicationTarget]
    snapshots: dict[str, WorkbenchRagEvalPromotionApplicationSnapshot] = field(
        default_factory=dict
    )
    revisions: dict[str, WorkbenchRagEvalEmbeddingRevisionReadModel] = field(
        default_factory=dict
    )
    persist_calls: list[WorkbenchRagEvalEmbeddingRevision] = field(default_factory=list)
    persist_order: list[str] = field(default_factory=list)
    fail_runtime_entry_id: str | None = None

    def __post_init__(self) -> None:
        grouped: dict[str, list[WorkbenchRagEvalPromotionApplicationTarget]] = {}
        for target in self.targets:
            grouped.setdefault(target.target_runtime_entry_id, []).append(target)
        for runtime_entry_id, group in grouped.items():
            self.snapshots[runtime_entry_id] = _snapshot(tuple(group))

    async def list_promotion_application_targets_for_ids(
        self,
        *,
        project_id: str,
        promotion_ids,
    ):
        assert project_id == "project-1"
        requested = set(promotion_ids)
        return tuple(
            target for target in self.targets if target.promotion_id in requested
        )

    async def list_promotion_application_targets_for_run(
        self,
        *,
        project_id: str,
        run_id: str,
    ):
        assert project_id == "project-1"
        return tuple(target for target in self.targets if target.run_id == run_id)

    async def load_promotion_application_group(
        self,
        *,
        project_id: str,
        promotion_ids,
        target_runtime_entry_id: str,
        embedding_model_id: str,
    ):
        assert project_id == "project-1"
        assert embedding_model_id == "model-1"
        snapshot = self.snapshots.get(target_runtime_entry_id)
        if snapshot is None:
            return None
        requested = set(promotion_ids)
        candidates = tuple(
            candidate
            for candidate in snapshot.candidates
            if candidate.promotion_id in requested
        )
        return replace(snapshot, candidates=candidates)

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
                and revision.status
                is WorkbenchRagEvalEmbeddingRevisionStatus.PENDING_VERIFICATION
            ):
                return revision
        return None

    async def persist_promotion_application_revision(
        self,
        *,
        snapshot: WorkbenchRagEvalPromotionApplicationSnapshot,
        revision: WorkbenchRagEvalEmbeddingRevision,
    ) -> WorkbenchRagEvalEmbeddingRevisionReadModel:
        self.persist_order.append("revision")
        if snapshot.runtime_entry_id == self.fail_runtime_entry_id:
            raise WorkbenchRagEvalPromotionConflictError(
                "injected target failure",
                code=WorkbenchRagEvalPromotionConflictCode.PERSISTENCE_CONFLICT,
                promotion_ids=revision.promotion_ids,
                runtime_entry_id=revision.runtime_entry_id,
            )
        self.persist_calls.append(revision)
        read_model = WorkbenchRagEvalEmbeddingRevisionReadModel(
            revision_id=revision.revision_id,
            project_id=revision.project_id,
            runtime_entry_id=revision.runtime_entry_id,
            source_rag_eval_run_id=revision.source_rag_eval_run_id,
            promotion_ids=tuple(sorted(revision.promotion_ids)),
            status=revision.status,
            previous_promoted_questions=revision.previous_promoted_questions,
            new_promoted_questions=revision.new_promoted_questions,
            created_at=revision.created_at,
            accepted_at=None,
            regression_failed_at=None,
            rolled_back_at=None,
        )
        self.revisions[read_model.revision_id] = read_model
        applied_ids = set(revision.promotion_ids)
        self.targets = [
            replace(
                target,
                status=WorkbenchRagEvalPromotionStatus.APPLIED,
            )
            if target.promotion_id in applied_ids
            else target
            for target in self.targets
        ]
        self.snapshots[snapshot.runtime_entry_id] = replace(
            snapshot,
            possible_questions=revision.new_promoted_questions,
            embedding_text=revision.new_embedding_text,
            embedding=revision.new_embedding,
            runtime_hash=revision.new_runtime_hash,
            active_revision_id=revision.revision_id,
            candidates=tuple(
                replace(
                    candidate,
                    status=WorkbenchRagEvalPromotionStatus.APPLIED,
                )
                if candidate.promotion_id in applied_ids
                else candidate
                for candidate in snapshot.candidates
            ),
        )
        self.persist_order.append("runtime-and-promotions")
        return read_model


def _service(
    repo: FakeRepository,
    embedding: FakeEmbeddingPort,
) -> ApplyWorkbenchRagEvalPromotionsBatch:
    return ApplyWorkbenchRagEvalPromotionsBatch(
        rag_eval_repository=repo,
        embedding_generation_port=embedding,
        embedding_model_id="model-1",
        embedding_dimensions=3,
        embedding_text_builder=PromotedQuestionRuntimeEmbeddingTextBuilder(),
        application_policy=WorkbenchRagEvalPromotionApplicationPolicy(
            WorkbenchRagEvalPromotionApplicationPolicyConfig(
                max_active_promoted_questions_per_runtime_entry=12
            )
        ),
    )


@pytest.mark.asyncio
async def test_single_approved_application_uses_grouped_service_and_one_revision() -> (
    None
):
    repo = FakeRepository([_target("promotion-1")])
    embedding = FakeEmbeddingPort()
    result = await ApplyWorkbenchRagEvalPromotion(
        grouped_application=_service(repo, embedding)
    ).execute(
        project_id="project-1",
        promotion_id="promotion-1",
        applied_at=NOW,
    )

    assert result.applied_count == 1
    assert result.embedding_recalculation_count == 1
    assert len(result.revisions) == 1
    assert len(embedding.calls) == 1
    assert len(repo.persist_calls) == 1
    assert repo.persist_order == ["revision", "runtime-and-promotions"]


@pytest.mark.asyncio
async def test_single_candidate_cannot_apply_and_does_not_embed() -> None:
    repo = FakeRepository(
        [_target("promotion-1", status=WorkbenchRagEvalPromotionStatus.CANDIDATE)]
    )
    embedding = FakeEmbeddingPort()

    with pytest.raises(WorkbenchRagEvalPromotionConflictError):
        await ApplyWorkbenchRagEvalPromotion(
            grouped_application=_service(repo, embedding)
        ).execute(
            project_id="project-1",
            promotion_id="promotion-1",
            applied_at=NOW,
        )

    assert embedding.calls == []
    assert repo.persist_calls == []


@pytest.mark.asyncio
async def test_repeated_single_request_returns_pending_revision_without_reembedding() -> (
    None
):
    repo = FakeRepository([_target("promotion-1")])
    embedding = FakeEmbeddingPort()
    single = ApplyWorkbenchRagEvalPromotion(
        grouped_application=_service(repo, embedding)
    )

    first = await single.execute(
        project_id="project-1",
        promotion_id="promotion-1",
        applied_at=NOW,
    )
    second = await single.execute(
        project_id="project-1",
        promotion_id="promotion-1",
        applied_at=NOW,
    )

    assert first.revisions[0].revision_id == second.revisions[0].revision_id
    assert second.revisions[0].idempotent is True
    assert len(embedding.calls) == 1
    assert len(repo.persist_calls) == 1


@pytest.mark.asyncio
async def test_two_approved_candidates_same_target_use_one_embedding_and_revision() -> (
    None
):
    repo = FakeRepository(
        [
            _target("promotion-1", question="Q1?"),
            _target("promotion-2", question="Q2?"),
        ]
    )
    embedding = FakeEmbeddingPort()
    result = await _service(repo, embedding).execute(
        project_id="project-1",
        mode="selected",
        promotion_ids=("promotion-1", "promotion-2"),
        run_id=None,
        applied_at=NOW,
    )

    assert result.applied_count == 2
    assert result.embedding_recalculation_count == 1
    assert len(result.revisions) == 1
    assert result.revisions[0].promotion_ids == ("promotion-1", "promotion-2")
    assert len(embedding.calls) == 1


@pytest.mark.asyncio
async def test_candidates_for_two_targets_use_two_embeddings_and_revisions() -> None:
    repo = FakeRepository(
        [
            _target("promotion-1", runtime_entry_id="entry-1"),
            _target("promotion-2", runtime_entry_id="entry-2"),
        ]
    )
    embedding = FakeEmbeddingPort()
    result = await _service(repo, embedding).execute(
        project_id="project-1",
        mode="selected",
        promotion_ids=("promotion-1", "promotion-2"),
        run_id=None,
        applied_at=NOW,
    )

    assert result.applied_count == 2
    assert result.embedding_recalculation_count == 2
    assert len(result.revisions) == 2
    assert len(embedding.calls) == 2


@pytest.mark.asyncio
async def test_mixed_candidate_and_approved_never_leaks_candidate_alias() -> None:
    repo = FakeRepository(
        [
            _target(
                "promotion-1",
                runtime_entry_id="entry-1",
                question="Forbidden candidate alias?",
                status=WorkbenchRagEvalPromotionStatus.CANDIDATE,
            ),
            _target(
                "promotion-2",
                runtime_entry_id="entry-2",
                question="Approved alias?",
            ),
        ]
    )
    embedding = FakeEmbeddingPort()
    result = await _service(repo, embedding).execute(
        project_id="project-1",
        mode="selected",
        promotion_ids=("promotion-1", "promotion-2"),
        run_id=None,
        applied_at=NOW,
    )

    assert result.applied_count == 1
    assert result.revisions[0].promotion_ids == ("promotion-2",)
    assert "Forbidden candidate alias?" not in embedding.calls[0].texts[0]
    assert any(error.promotion_ids == ("promotion-1",) for error in result.errors)


@pytest.mark.asyncio
async def test_active_revision_on_one_target_does_not_corrupt_other_target() -> None:
    repo = FakeRepository(
        [
            _target("promotion-1", runtime_entry_id="entry-1"),
            _target("promotion-2", runtime_entry_id="entry-2"),
        ]
    )
    repo.snapshots["entry-1"] = replace(
        repo.snapshots["entry-1"],
        active_revision_id="active-revision",
    )
    embedding = FakeEmbeddingPort()
    result = await _service(repo, embedding).execute(
        project_id="project-1",
        mode="selected",
        promotion_ids=("promotion-1", "promotion-2"),
        run_id=None,
        applied_at=NOW,
    )

    assert result.applied_count == 1
    assert result.revisions[0].runtime_entry_id == "entry-2"
    assert len(embedding.calls) == 1
    assert any(error.runtime_entry_id == "entry-1" for error in result.errors)


@pytest.mark.asyncio
async def test_partial_group_failure_is_per_target_transactional_and_explicit() -> None:
    repo = FakeRepository(
        [
            _target("promotion-1", runtime_entry_id="entry-1"),
            _target("promotion-2", runtime_entry_id="entry-2"),
        ],
        fail_runtime_entry_id="entry-1",
    )
    embedding = FakeEmbeddingPort()
    result = await _service(repo, embedding).execute(
        project_id="project-1",
        mode="selected",
        promotion_ids=("promotion-1", "promotion-2"),
        run_id=None,
        applied_at=NOW,
    )

    assert result.applied_count == 1
    assert result.revisions[0].runtime_entry_id == "entry-2"
    assert any(error.runtime_entry_id == "entry-1" for error in result.errors)
    assert len(embedding.calls) == 2


@pytest.mark.asyncio
async def test_concurrent_apply_same_target_creates_one_revision_and_one_mutation() -> (
    None
):
    import asyncio

    repo = FakeRepository([_target("promotion-1")])
    embedding = FakeEmbeddingPort()
    service = _service(repo, embedding)

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

    assert len(repo.persist_calls) == 1
    assert len(repo.revisions) == 1
    assert len(embedding.calls) == 1
    assert first.revisions[0].revision_id == second.revisions[0].revision_id
    assert {first.revisions[0].idempotent, second.revisions[0].idempotent} == {
        False,
        True,
    }
