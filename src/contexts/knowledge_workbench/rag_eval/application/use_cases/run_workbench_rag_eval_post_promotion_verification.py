from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from src.contexts.embedding_runtime.application.ports.embedding_generation_port import (
    EmbeddingGenerationPort,
    EmbeddingGenerationRequest,
)
from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval_embedding_revision import (
    WorkbenchRagEvalEmbeddingRevision,
)
from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval_verification import (
    WorkbenchRagEvalVerificationMetrics,
    WorkbenchRagEvalVerificationOutcomePair,
    WorkbenchRagEvalVerificationPolicyDecision,
    WorkbenchRagEvalVerificationQuery,
    WorkbenchRagEvalVerificationSearchObservation,
)
from src.contexts.knowledge_workbench.rag_eval.application.policies.workbench_rag_eval_promotion_verification_policy import (
    WorkbenchRagEvalPromotionVerificationPolicy,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.handle_run_workbench_rag_eval_post_promotion_verification_command import (
    RunWorkbenchRagEvalPostPromotionVerificationCommand,
    RunWorkbenchRagEvalPostPromotionVerificationResult,
)
from src.contexts.workflow_runtime.domain.entities.workflow_command import (
    WorkflowCommandStatus,
)


class WorkbenchRagEvalPostPromotionVerificationRepositoryPort(Protocol):
    async def get_embedding_revision_for_verification(
        self,
        *,
        project_id: str,
        revision_id: str,
    ) -> WorkbenchRagEvalEmbeddingRevision: ...

    async def start_post_promotion_verification(
        self,
        *,
        revision: WorkbenchRagEvalEmbeddingRevision,
        started_at: datetime,
    ) -> int: ...

    async def list_pending_post_promotion_verification_queries(
        self,
        *,
        revision: WorkbenchRagEvalEmbeddingRevision,
        limit: int,
    ) -> tuple[WorkbenchRagEvalVerificationQuery, ...]: ...

    async def observe_post_promotion_verification_query(
        self,
        *,
        revision: WorkbenchRagEvalEmbeddingRevision,
        query: WorkbenchRagEvalVerificationQuery,
        query_embedding: tuple[float, ...],
        use_new_embedding: bool,
        limit: int,
    ) -> WorkbenchRagEvalVerificationSearchObservation: ...

    async def persist_post_promotion_verification_outcomes(
        self,
        *,
        revision: WorkbenchRagEvalEmbeddingRevision,
        outcome_pairs: tuple[WorkbenchRagEvalVerificationOutcomePair, ...],
        observed_at: datetime,
    ) -> None: ...

    async def count_remaining_post_promotion_verification_queries(
        self,
        *,
        revision: WorkbenchRagEvalEmbeddingRevision,
    ) -> int: ...

    async def list_post_promotion_verification_outcome_pairs(
        self,
        *,
        revision: WorkbenchRagEvalEmbeddingRevision,
    ) -> tuple[WorkbenchRagEvalVerificationOutcomePair, ...]: ...

    async def complete_post_promotion_verification(
        self,
        *,
        revision: WorkbenchRagEvalEmbeddingRevision,
        metrics: WorkbenchRagEvalVerificationMetrics,
        policy_decision: WorkbenchRagEvalVerificationPolicyDecision,
        completed_at: datetime,
    ) -> None: ...

    async def fail_post_promotion_verification(
        self,
        *,
        revision: WorkbenchRagEvalEmbeddingRevision,
        error_message: str,
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class RunWorkbenchRagEvalPostPromotionVerification:
    repository: WorkbenchRagEvalPostPromotionVerificationRepositoryPort
    embedding_generation_port: EmbeddingGenerationPort
    embedding_model_id: str
    embedding_dimensions: int
    policy: WorkbenchRagEvalPromotionVerificationPolicy
    top_k: int = 5
    batch_limit: int = 20

    async def execute(
        self,
        command: RunWorkbenchRagEvalPostPromotionVerificationCommand,
    ) -> RunWorkbenchRagEvalPostPromotionVerificationResult:
        workflow_command = command.workflow_command
        if workflow_command.status is not WorkflowCommandStatus.PENDING:
            raise ValueError("post-promotion verification command must be pending")
        project_id = _payload_text(workflow_command.payload, "project_id")
        revision_id = _payload_text(workflow_command.payload, "revision_id")
        workflow_run_id = _payload_text(workflow_command.payload, "workflow_run_id")
        rag_eval_run_id = _payload_text(workflow_command.payload, "rag_eval_run_id")
        if workflow_run_id != workflow_command.workflow_run_id:
            raise ValueError("workflow command payload run id does not match command")
        if rag_eval_run_id != workflow_run_id:
            raise ValueError("RAG Eval run id must match workflow run id")
        if self.top_k < 5:
            raise ValueError("post-promotion verification top_k must be at least 5")
        batch_limit = _payload_int(
            workflow_command.payload,
            "batch_limit",
            self.batch_limit,
        )
        if batch_limit <= 0:
            raise ValueError("post-promotion verification batch_limit must be positive")
        batch_index = _payload_int(workflow_command.payload, "batch_index", 0)
        batch_key = _payload_text(
            workflow_command.payload,
            "batch_key",
            fallback=f"{revision_id}:batch:{batch_index}",
        )

        revision = await self.repository.get_embedding_revision_for_verification(
            project_id=project_id,
            revision_id=revision_id,
        )
        total_query_count = await self.repository.start_post_promotion_verification(
            revision=revision,
            started_at=workflow_command.updated_at,
        )
        if total_query_count <= 0:
            raise ValueError("post-promotion verification requires persisted queries")

        try:
            queries = (
                await self.repository.list_pending_post_promotion_verification_queries(
                    revision=revision,
                    limit=batch_limit,
                )
            )
            embeddings = await self._embed_queries(queries) if queries else ()
            pairs = await self._observe_pairs(
                revision=revision,
                queries=queries,
                embeddings=embeddings,
            )
            await self.repository.persist_post_promotion_verification_outcomes(
                revision=revision,
                outcome_pairs=pairs,
                observed_at=workflow_command.updated_at,
            )
            remaining_count = await self.repository.count_remaining_post_promotion_verification_queries(
                revision=revision,
            )
            decision = None
            status = "running"
            metrics: WorkbenchRagEvalVerificationMetrics | None = None
            if remaining_count == 0:
                all_pairs = await self.repository.list_post_promotion_verification_outcome_pairs(
                    revision=revision,
                )
                metrics = WorkbenchRagEvalVerificationMetrics.from_outcome_pairs(
                    all_pairs
                )
                decision = self.policy.decide(metrics)
                await self.repository.complete_post_promotion_verification(
                    revision=revision,
                    metrics=metrics,
                    policy_decision=decision,
                    completed_at=workflow_command.updated_at,
                )
                status = (
                    "passed" if not decision.failure_reasons else "regression_failed"
                )
        except Exception as exc:
            await self.repository.fail_post_promotion_verification(
                revision=revision,
                error_message=str(exc),
            )
            raise

        return RunWorkbenchRagEvalPostPromotionVerificationResult(
            workflow_run_id=workflow_run_id,
            revision_id=revision.revision_id,
            runtime_entry_id=revision.runtime_entry_id,
            batch_key=batch_key,
            batch_limit=batch_limit,
            processed_count=len(queries),
            remaining_count=remaining_count,
            total_query_count=total_query_count,
            terminal=remaining_count == 0,
            status=status,
            decision=decision.decision.value if decision is not None else None,
            failure_reasons=tuple(reason.value for reason in decision.failure_reasons)
            if decision is not None
            else (),
        )

    async def _embed_queries(
        self,
        queries: tuple[WorkbenchRagEvalVerificationQuery, ...],
    ) -> tuple[tuple[float, ...], ...]:
        result = await self.embedding_generation_port.embed(
            EmbeddingGenerationRequest(
                texts=tuple(query.query_text for query in queries),
                model_id=self.embedding_model_id,
                expected_dimensions=self.embedding_dimensions,
                task="retrieval.query",
            )
        )
        if result.model_id != self.embedding_model_id:
            raise ValueError("verification query embedding model mismatch")
        if result.dimensions != self.embedding_dimensions:
            raise ValueError("verification query embedding dimensions mismatch")
        if len(result.embeddings) != len(queries):
            raise ValueError("verification query embedding count mismatch")
        return result.embeddings

    async def _observe_pairs(
        self,
        *,
        revision: WorkbenchRagEvalEmbeddingRevision,
        queries: tuple[WorkbenchRagEvalVerificationQuery, ...],
        embeddings: tuple[tuple[float, ...], ...],
    ) -> tuple[WorkbenchRagEvalVerificationOutcomePair, ...]:
        pairs: list[WorkbenchRagEvalVerificationOutcomePair] = []
        for query, query_embedding in zip(queries, embeddings, strict=True):
            before = await self.repository.observe_post_promotion_verification_query(
                revision=revision,
                query=query,
                query_embedding=query_embedding,
                use_new_embedding=False,
                limit=self.top_k,
            )
            after = await self.repository.observe_post_promotion_verification_query(
                revision=revision,
                query=query,
                query_embedding=query_embedding,
                use_new_embedding=True,
                limit=self.top_k,
            )
            pairs.append(_pair(query=query, before=before, after=after))
        return tuple(pairs)


def _pair(
    *,
    query: WorkbenchRagEvalVerificationQuery,
    before: WorkbenchRagEvalVerificationSearchObservation,
    after: WorkbenchRagEvalVerificationSearchObservation,
) -> WorkbenchRagEvalVerificationOutcomePair:
    return WorkbenchRagEvalVerificationOutcomePair(
        verification_query_id=query.verification_query_id,
        dataset_role=query.dataset_role,
        expected_runtime_entry_id=query.expected_runtime_entry_id,
        before_expected_rank=before.expected_rank,
        after_expected_rank=after.expected_rank,
        before_expected_score=before.expected_score,
        after_expected_score=after.expected_score,
        before_best_competitor_runtime_entry_id=(
            before.best_competitor_runtime_entry_id
        ),
        after_best_competitor_runtime_entry_id=after.best_competitor_runtime_entry_id,
        before_score_margin=before.score_margin,
        after_score_margin=after.score_margin,
        before_classification=before.classification,
        after_classification=after.classification,
    )


def _payload_text(payload: object, key: str, fallback: str | None = None) -> str:
    if not isinstance(payload, Mapping):
        raise TypeError("workflow command payload must be mapping")
    value = payload.get(key, fallback)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"workflow command payload.{key} must be non-empty")
    return value.strip()


def _payload_int(payload: object, key: str, default: int) -> int:
    if not isinstance(payload, Mapping):
        raise TypeError("workflow command payload must be mapping")
    value = payload.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"workflow command payload.{key} must be int")
    if value < 0:
        raise ValueError(f"workflow command payload.{key} must be non-negative")
    return value
