from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from src.contexts.embedding_runtime.application.ports.embedding_generation_port import (
    EmbeddingGenerationRequest,
    EmbeddingGenerationResult,
)
from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval import (
    WorkbenchRagEvalPromotionApplicationTarget,
    WorkbenchRagEvalPromotionApplyResult,
    WorkbenchRagEvalPromotionStatus,
)
from src.contexts.knowledge_workbench.rag_eval.application.policies.promoted_question_runtime_embedding_text_builder import (
    PromotedQuestionRuntimeEmbeddingTextBuilder,
)
from src.contexts.knowledge_workbench.rag_eval.application.use_cases.apply_workbench_rag_eval_promotions_batch import (
    ApplyWorkbenchRagEvalPromotionsBatch,
)


def _now() -> datetime:
    return datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)


def _target(
    promotion_id: str,
    *,
    runtime_entry_id: str = "entry-1",
    question: str = "How to ask?",
    status: WorkbenchRagEvalPromotionStatus = WorkbenchRagEvalPromotionStatus.CANDIDATE,
) -> WorkbenchRagEvalPromotionApplicationTarget:
    return WorkbenchRagEvalPromotionApplicationTarget(
        promotion_id=promotion_id,
        run_id="run-1",
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
        existing_embedding_text=f"Claim:\\nClaim {runtime_entry_id}\\n\\nPossible questions:\\n- Existing?",
    )


@dataclass(slots=True)
class FakeEmbeddingPort:
    calls: list[EmbeddingGenerationRequest] = field(default_factory=list)

    async def embed(
        self, request: EmbeddingGenerationRequest
    ) -> EmbeddingGenerationResult:
        self.calls.append(request)
        return EmbeddingGenerationResult(
            embeddings=((0.1, 0.2, 0.3),),
            model_id=request.model_id,
            dimensions=request.expected_dimensions,
        )


@dataclass(slots=True)
class FakeRepository:
    targets: tuple[WorkbenchRagEvalPromotionApplicationTarget, ...]
    applied_groups: list[tuple[str, ...]] = field(default_factory=list)

    async def list_promotion_application_targets_for_ids(
        self, *, project_id: str, promotion_ids
    ):
        assert project_id == "project-1"
        requested = set(promotion_ids)
        return tuple(
            target for target in self.targets if target.promotion_id in requested
        )

    async def list_promotion_application_targets_for_run(
        self, *, project_id: str, run_id: str
    ):
        assert project_id == "project-1"
        assert run_id == "run-1"
        return self.targets

    async def apply_promotion_candidates_for_target(self, **kwargs):
        ids = tuple(kwargs["promotion_ids"])
        self.applied_groups.append(ids)
        return tuple(
            WorkbenchRagEvalPromotionApplyResult(
                promotion_id=promotion_id,
                run_id="run-1",
                question_id=f"question-{promotion_id}",
                project_id=kwargs["project_id"],
                target_runtime_entry_id=kwargs["target_runtime_entry_id"],
                target_fact_id=f"fact-{kwargs['target_runtime_entry_id']}",
                question="applied",
                status=WorkbenchRagEvalPromotionStatus.APPLIED,
                possible_question_count=3,
                embedding_model_id=kwargs["embedding_model_id"],
                embedding_count=1,
                applied_at=kwargs["applied_at"],
            )
            for promotion_id in ids
        )


@pytest.mark.asyncio
async def test_selected_batch_groups_same_runtime_entry_into_one_embedding() -> None:
    repo = FakeRepository(
        targets=(
            _target("promotion-1", runtime_entry_id="entry-1", question="Q1?"),
            _target("promotion-2", runtime_entry_id="entry-1", question="Q2?"),
        )
    )
    embedding = FakeEmbeddingPort()

    result = await ApplyWorkbenchRagEvalPromotionsBatch(
        rag_eval_repository=repo,
        embedding_generation_port=embedding,
        embedding_model_id="test-model",
        embedding_dimensions=3,
        embedding_text_builder=PromotedQuestionRuntimeEmbeddingTextBuilder(),
    ).execute(
        project_id="project-1",
        mode="selected",
        promotion_ids=("promotion-1", "promotion-2"),
        run_id=None,
        applied_at=_now(),
    )

    assert result.requested_count == 2
    assert result.applied_count == 2
    assert result.skipped_count == 0
    assert result.embedding_recalculation_count == 1
    assert repo.applied_groups == [("promotion-1", "promotion-2")]
    assert len(embedding.calls) == 1


@pytest.mark.asyncio
async def test_all_candidates_for_run_skips_applied_and_groups_changed_surfaces() -> (
    None
):
    repo = FakeRepository(
        targets=(
            _target("promotion-1", runtime_entry_id="entry-1"),
            _target("promotion-2", runtime_entry_id="entry-1"),
            _target("promotion-3", runtime_entry_id="entry-2"),
            _target(
                "promotion-4",
                runtime_entry_id="entry-2",
                status=WorkbenchRagEvalPromotionStatus.APPLIED,
            ),
        )
    )
    embedding = FakeEmbeddingPort()

    result = await ApplyWorkbenchRagEvalPromotionsBatch(
        rag_eval_repository=repo,
        embedding_generation_port=embedding,
        embedding_model_id="test-model",
        embedding_dimensions=3,
        embedding_text_builder=PromotedQuestionRuntimeEmbeddingTextBuilder(),
    ).execute(
        project_id="project-1",
        mode="all_candidates_for_run",
        promotion_ids=(),
        run_id="run-1",
        applied_at=_now(),
    )

    assert result.requested_count == 4
    assert result.applied_count == 3
    assert result.skipped_count == 1
    assert result.embedding_recalculation_count == 2
    assert len(embedding.calls) == 2
