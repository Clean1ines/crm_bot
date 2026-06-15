from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from collections.abc import Sequence

import pytest

from src.contexts.embedding_runtime.application.ports.embedding_generation_port import (
    EmbeddingGenerationRequest,
    EmbeddingGenerationResult,
)
from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval import (
    WorkbenchRagEvalPromotionApplicationTarget,
    WorkbenchRagEvalPromotionApplyResult,
    WorkbenchRagEvalPromotionCandidateDetails,
    WorkbenchRagEvalPromotionStatus,
)
from src.contexts.knowledge_workbench.rag_eval.application.policies.promoted_question_runtime_embedding_text_builder import (
    PromotedQuestionRuntimeEmbeddingTextBuilder,
)
from src.contexts.knowledge_workbench.rag_eval.application.use_cases.apply_workbench_rag_eval_promotion import (
    ApplyWorkbenchRagEvalPromotion,
    WorkbenchRagEvalPromotionConflictError,
    WorkbenchRagEvalPromotionEmbeddingError,
)


def _now() -> datetime:
    return datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)


@dataclass(slots=True)
class FakeEmbeddingPort:
    vector: tuple[float, ...] = (0.1, 0.2, 0.3)
    seen_request: EmbeddingGenerationRequest | None = None

    async def embed(
        self, request: EmbeddingGenerationRequest
    ) -> EmbeddingGenerationResult:
        self.seen_request = request
        return EmbeddingGenerationResult(
            embeddings=(self.vector,),
            model_id=request.model_id,
            dimensions=request.expected_dimensions,
        )


@dataclass(slots=True)
class FakeRepository:
    status: WorkbenchRagEvalPromotionStatus = WorkbenchRagEvalPromotionStatus.CANDIDATE
    applied_embedding_text: str | None = None
    applied_embedding: Sequence[float] | None = None

    async def get_promotion_candidate(self, *, project_id: str, promotion_id: str):
        return WorkbenchRagEvalPromotionCandidateDetails(
            promotion_id=promotion_id,
            run_id="run-1",
            question_id="question-1",
            project_id=project_id,
            target_runtime_entry_id="entry-1",
            target_fact_id="fact-1",
            question="Как спросить иначе?",
            status=self.status,
            created_at=_now(),
            applied_at=None,
        )

    async def get_promotion_application_target(
        self, *, project_id: str, promotion_id: str
    ):
        return WorkbenchRagEvalPromotionApplicationTarget(
            promotion_id=promotion_id,
            run_id="run-1",
            question_id="question-1",
            project_id=project_id,
            target_runtime_entry_id="entry-1",
            target_fact_id="fact-1",
            question="Как спросить иначе?",
            status=self.status,
            claim="Claim text",
            runtime_possible_questions=("Existing?",),
            fact_possible_questions=("Existing?",),
            exclusion_scope="Not X",
            existing_embedding_text=(
                "Claim:\\nClaim text\\n\\nPossible questions:\\n- Existing?\\n\\n"
                "Exclusion scope:\\nNot X\\n\\nEvidence:\\nEvidence text"
            ),
        )

    async def apply_promotion_candidate(self, **kwargs):
        self.applied_embedding_text = kwargs["embedding_text"]
        self.applied_embedding = kwargs["embedding"]
        return WorkbenchRagEvalPromotionApplyResult(
            promotion_id=kwargs["promotion_id"],
            run_id="run-1",
            question_id="question-1",
            project_id=kwargs["project_id"],
            target_runtime_entry_id="entry-1",
            target_fact_id="fact-1",
            question="Как спросить иначе?",
            status=WorkbenchRagEvalPromotionStatus.APPLIED,
            possible_question_count=2,
            embedding_model_id=kwargs["embedding_model_id"],
            embedding_count=1,
            applied_at=kwargs["applied_at"],
        )


@pytest.mark.asyncio
async def test_apply_promotion_builds_embedding_and_applies_candidate() -> None:
    repository = FakeRepository()
    embedding_port = FakeEmbeddingPort()

    result = await ApplyWorkbenchRagEvalPromotion(
        rag_eval_repository=repository,
        embedding_generation_port=embedding_port,
        embedding_model_id="test-model",
        embedding_dimensions=3,
        embedding_text_builder=PromotedQuestionRuntimeEmbeddingTextBuilder(),
    ).execute(
        project_id="11111111-1111-1111-1111-111111111111",
        promotion_id="promotion-1",
        applied_at=_now(),
    )

    assert result.status is WorkbenchRagEvalPromotionStatus.APPLIED
    assert result.possible_question_count == 2
    assert embedding_port.seen_request is not None
    assert embedding_port.seen_request.task == "retrieval.passage"
    assert repository.applied_embedding_text is not None
    assert "Как спросить иначе?" in repository.applied_embedding_text
    assert "answer_text" not in repository.applied_embedding_text


@pytest.mark.asyncio
async def test_apply_promotion_rejects_already_applied_candidate() -> None:
    with pytest.raises(WorkbenchRagEvalPromotionConflictError):
        await ApplyWorkbenchRagEvalPromotion(
            rag_eval_repository=FakeRepository(
                status=WorkbenchRagEvalPromotionStatus.APPLIED
            ),
            embedding_generation_port=FakeEmbeddingPort(),
            embedding_model_id="test-model",
            embedding_dimensions=3,
            embedding_text_builder=PromotedQuestionRuntimeEmbeddingTextBuilder(),
        ).execute(
            project_id="11111111-1111-1111-1111-111111111111",
            promotion_id="promotion-1",
            applied_at=_now(),
        )


@pytest.mark.asyncio
async def test_apply_promotion_rejects_bad_embedding_dimensions() -> None:
    with pytest.raises(WorkbenchRagEvalPromotionEmbeddingError):
        await ApplyWorkbenchRagEvalPromotion(
            rag_eval_repository=FakeRepository(),
            embedding_generation_port=FakeEmbeddingPort(vector=(0.1, 0.2)),
            embedding_model_id="test-model",
            embedding_dimensions=3,
            embedding_text_builder=PromotedQuestionRuntimeEmbeddingTextBuilder(),
        ).execute(
            project_id="11111111-1111-1111-1111-111111111111",
            promotion_id="promotion-1",
            applied_at=_now(),
        )
