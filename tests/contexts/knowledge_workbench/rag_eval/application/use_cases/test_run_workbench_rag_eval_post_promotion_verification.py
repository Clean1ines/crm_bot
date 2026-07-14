from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from src.contexts.embedding_runtime.application.ports.embedding_generation_port import (
    EmbeddingGenerationRequest,
    EmbeddingGenerationResult,
)
from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval import (
    WorkbenchRagEvalRetrievalClassification,
)
from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval_embedding_revision import (
    WORKBENCH_RUNTIME_EMBEDDING_DIMENSIONS,
    WorkbenchRagEvalEmbeddingRevision,
    WorkbenchRagEvalEmbeddingRevisionStatus,
)
from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval_verification import (
    WorkbenchRagEvalVerificationDatasetRole,
    WorkbenchRagEvalVerificationMetrics,
    WorkbenchRagEvalVerificationOutcomePair,
    WorkbenchRagEvalVerificationPolicyDecision,
    WorkbenchRagEvalVerificationQuery,
    WorkbenchRagEvalVerificationSearchObservation,
)
from src.contexts.knowledge_workbench.rag_eval.application.policies.workbench_rag_eval_promotion_verification_policy import (
    WorkbenchRagEvalPromotionVerificationPolicy,
)
from src.contexts.knowledge_workbench.rag_eval.application.use_cases.run_workbench_rag_eval_post_promotion_verification import (
    RunWorkbenchRagEvalPostPromotionVerification,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.handle_run_workbench_rag_eval_post_promotion_verification_command import (
    RunWorkbenchRagEvalPostPromotionVerificationCommand,
)
from src.contexts.workflow_runtime.domain.entities.workflow_command import (
    WorkflowCommand,
    WorkflowCommandStatus,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_command_id import (
    WorkflowCommandId,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_idempotency_key import (
    WorkflowIdempotencyKey,
)


NOW = datetime(2026, 7, 14, 12, tzinfo=timezone.utc)
PROJECT_ID = "11111111-1111-1111-1111-111111111111"


@dataclass(slots=True)
class FakePostPromotionVerificationRepository:
    observed_calls: list[tuple[str, bool]] = field(default_factory=list)
    persisted_batches: list[
        tuple[tuple[WorkbenchRagEvalVerificationOutcomePair, ...], datetime]
    ] = field(default_factory=list)
    completed: (
        tuple[
            WorkbenchRagEvalVerificationMetrics,
            WorkbenchRagEvalVerificationPolicyDecision,
            datetime,
        ]
        | None
    ) = None
    failed: str | None = None
    queries: tuple[WorkbenchRagEvalVerificationQuery, ...] = field(
        default_factory=lambda: (_query(),)
    )
    persisted_query_ids: set[str] = field(default_factory=set)

    async def get_embedding_revision_for_verification(
        self,
        *,
        project_id: str,
        revision_id: str,
    ) -> WorkbenchRagEvalEmbeddingRevision:
        assert project_id == PROJECT_ID
        assert revision_id == "revision-1"
        return _revision()

    async def start_post_promotion_verification(
        self,
        *,
        revision: WorkbenchRagEvalEmbeddingRevision,
        started_at: datetime,
    ) -> int:
        assert revision.revision_id == "revision-1"
        assert started_at == NOW
        return len(self.queries)

    async def list_pending_post_promotion_verification_queries(
        self,
        *,
        revision: WorkbenchRagEvalEmbeddingRevision,
        limit: int,
    ) -> tuple[WorkbenchRagEvalVerificationQuery, ...]:
        assert revision.revision_id == "revision-1"
        return tuple(
            query
            for query in self.queries
            if query.verification_query_id not in self.persisted_query_ids
        )[:limit]

    async def observe_post_promotion_verification_query(
        self,
        *,
        revision: WorkbenchRagEvalEmbeddingRevision,
        query: WorkbenchRagEvalVerificationQuery,
        query_embedding: tuple[float, ...],
        use_new_embedding: bool,
        limit: int,
    ) -> WorkbenchRagEvalVerificationSearchObservation:
        assert revision.revision_id == "revision-1"
        assert query.verification_query_id.startswith("verification-query-")
        assert len(query_embedding) == WORKBENCH_RUNTIME_EMBEDDING_DIMENSIONS
        assert limit == 5
        self.observed_calls.append((query.query_text, use_new_embedding))
        if use_new_embedding:
            return WorkbenchRagEvalVerificationSearchObservation(
                expected_rank=3,
                expected_score=0.91,
                best_competitor_runtime_entry_id="competitor-1",
                best_competitor_fact_id="competitor-fact-1",
                best_competitor_score=0.6,
                score_margin=0.31,
                classification=WorkbenchRagEvalRetrievalClassification.PASS_STRONG,
            )
        return WorkbenchRagEvalVerificationSearchObservation(
            expected_rank=None,
            expected_score=None,
            best_competitor_runtime_entry_id="competitor-1",
            best_competitor_fact_id="competitor-fact-1",
            best_competitor_score=0.8,
            score_margin=-0.8,
            classification=WorkbenchRagEvalRetrievalClassification.MISS,
        )

    async def persist_post_promotion_verification_outcomes(
        self,
        *,
        revision: WorkbenchRagEvalEmbeddingRevision,
        outcome_pairs: tuple[WorkbenchRagEvalVerificationOutcomePair, ...],
        observed_at: datetime,
    ) -> None:
        assert revision.revision_id == "revision-1"
        self.persisted_batches.append((outcome_pairs, observed_at))
        self.persisted_query_ids.update(
            pair.verification_query_id for pair in outcome_pairs
        )

    async def count_remaining_post_promotion_verification_queries(
        self,
        *,
        revision: WorkbenchRagEvalEmbeddingRevision,
    ) -> int:
        assert revision.revision_id == "revision-1"
        return len(
            [
                query
                for query in self.queries
                if query.verification_query_id not in self.persisted_query_ids
            ]
        )

    async def list_post_promotion_verification_outcome_pairs(
        self,
        *,
        revision: WorkbenchRagEvalEmbeddingRevision,
    ) -> tuple[WorkbenchRagEvalVerificationOutcomePair, ...]:
        assert revision.revision_id == "revision-1"
        return tuple(pair for batch, _ in self.persisted_batches for pair in batch)

    async def complete_post_promotion_verification(
        self,
        *,
        revision: WorkbenchRagEvalEmbeddingRevision,
        metrics: WorkbenchRagEvalVerificationMetrics,
        policy_decision: WorkbenchRagEvalVerificationPolicyDecision,
        completed_at: datetime,
    ) -> None:
        assert revision.revision_id == "revision-1"
        self.completed = (metrics, policy_decision, completed_at)

    async def fail_post_promotion_verification(
        self,
        *,
        revision: WorkbenchRagEvalEmbeddingRevision,
        error_message: str,
    ) -> None:
        self.failed = error_message


@dataclass(slots=True)
class FakeEmbeddingGenerationPort:
    request: EmbeddingGenerationRequest | None = None

    async def embed(
        self,
        request: EmbeddingGenerationRequest,
    ) -> EmbeddingGenerationResult:
        self.request = request
        return EmbeddingGenerationResult(
            embeddings=tuple(_vector(0.5) for _ in request.texts),
            model_id="model-1",
            dimensions=WORKBENCH_RUNTIME_EMBEDDING_DIMENSIONS,
        )


async def test_post_promotion_verification_executor_persists_policy_decision() -> None:
    repository = FakePostPromotionVerificationRepository()
    embeddings = FakeEmbeddingGenerationPort()

    result = await RunWorkbenchRagEvalPostPromotionVerification(
        repository=repository,
        embedding_generation_port=embeddings,
        embedding_model_id="model-1",
        embedding_dimensions=WORKBENCH_RUNTIME_EMBEDDING_DIMENSIONS,
        policy=WorkbenchRagEvalPromotionVerificationPolicy(),
    ).execute(RunWorkbenchRagEvalPostPromotionVerificationCommand(_command()))

    assert result.processed_count == 1
    assert result.remaining_count == 0
    assert result.terminal is True
    assert embeddings.request is not None
    assert embeddings.request.texts == ("How do I verify this?",)
    assert repository.observed_calls == [
        ("How do I verify this?", False),
        ("How do I verify this?", True),
    ]
    assert repository.completed is not None
    assert len(repository.persisted_batches[0][0]) == 1
    metrics, decision, completed_at = repository.completed
    assert metrics.promoted.promoted_top3_improvement_count == 1
    assert decision.failure_reasons == ()
    assert completed_at == NOW
    assert repository.failed is None


async def test_post_promotion_verification_executor_processes_bounded_batches() -> None:
    repository = FakePostPromotionVerificationRepository(
        queries=tuple(_query(index) for index in range(45))
    )
    embeddings = FakeEmbeddingGenerationPort()
    use_case = RunWorkbenchRagEvalPostPromotionVerification(
        repository=repository,
        embedding_generation_port=embeddings,
        embedding_model_id="model-1",
        embedding_dimensions=WORKBENCH_RUNTIME_EMBEDDING_DIMENSIONS,
        policy=WorkbenchRagEvalPromotionVerificationPolicy(),
        batch_limit=20,
    )

    first = await use_case.execute(
        RunWorkbenchRagEvalPostPromotionVerificationCommand(_command(batch_index=0))
    )
    second = await use_case.execute(
        RunWorkbenchRagEvalPostPromotionVerificationCommand(_command(batch_index=1))
    )
    third = await use_case.execute(
        RunWorkbenchRagEvalPostPromotionVerificationCommand(_command(batch_index=2))
    )

    assert [first.processed_count, second.processed_count, third.processed_count] == [
        20,
        20,
        5,
    ]
    assert [first.remaining_count, second.remaining_count, third.remaining_count] == [
        25,
        5,
        0,
    ]
    assert [first.terminal, second.terminal, third.terminal] == [False, False, True]
    assert [len(batch) for batch, _ in repository.persisted_batches] == [20, 20, 5]
    assert repository.completed is not None


def _command(*, batch_index: int = 0) -> WorkflowCommand:
    return WorkflowCommand(
        command_id=WorkflowCommandId(f"workflow-command:verification-{batch_index}"),
        command_type="RunRagEvalPostPromotionVerification",
        workflow_run_id="run-1",
        idempotency_key=WorkflowIdempotencyKey(f"verification-{batch_index}"),
        payload={
            "workflow_run_id": "run-1",
            "rag_eval_run_id": "run-1",
            "project_id": PROJECT_ID,
            "revision_id": "revision-1",
            "runtime_entry_id": "entry-1",
            "batch_index": batch_index,
            "batch_limit": 20,
            "batch_key": f"revision-1:batch:{batch_index}",
        },
        status=WorkflowCommandStatus.PENDING,
        run_after=NOW,
        created_at=NOW,
        updated_at=NOW,
    )


def _revision() -> WorkbenchRagEvalEmbeddingRevision:
    return WorkbenchRagEvalEmbeddingRevision(
        revision_id="revision-1",
        project_id=PROJECT_ID,
        runtime_entry_id="entry-1",
        source_rag_eval_run_id="run-1",
        promotion_ids=("promotion-1",),
        status=WorkbenchRagEvalEmbeddingRevisionStatus.PENDING_VERIFICATION,
        previous_embedding_text="old text",
        new_embedding_text="new text",
        previous_embedding=_vector(0.1),
        new_embedding=_vector(0.2),
        previous_promoted_questions=("Old?",),
        new_promoted_questions=("Old?", "How do I verify this?"),
        embedding_model_id="model-1",
        embedding_dimensions=WORKBENCH_RUNTIME_EMBEDDING_DIMENSIONS,
        previous_runtime_hash="old-hash",
        new_runtime_hash="new-hash",
        created_at=NOW,
        accepted_at=None,
        regression_failed_at=None,
        rolled_back_at=None,
    )


def _query(index: int = 1) -> WorkbenchRagEvalVerificationQuery:
    return WorkbenchRagEvalVerificationQuery(
        verification_query_id=f"verification-query-{index}",
        revision_id="revision-1",
        run_id="run-1",
        project_id=PROJECT_ID,
        query_text="How do I verify this?"
        if index == 1
        else f"How do I verify {index}?",
        dataset_role=WorkbenchRagEvalVerificationDatasetRole.PROMOTED,
        expected_runtime_entry_id="entry-1",
        expected_fact_id="fact-1",
        source_runtime_entry_id="entry-1",
        question_id="question-1",
        source_outcome_id="outcome-1",
        promotion_id="promotion-1",
        created_at=NOW,
    )


def _vector(value: float) -> tuple[float, ...]:
    return (value,) * WORKBENCH_RUNTIME_EMBEDDING_DIMENSIONS
