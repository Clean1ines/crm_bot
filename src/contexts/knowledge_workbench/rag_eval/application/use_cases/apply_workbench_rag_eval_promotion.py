from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from collections.abc import Sequence

from src.contexts.embedding_runtime.application.ports.embedding_generation_port import (
    EmbeddingGenerationPort,
    EmbeddingGenerationRequest,
)
from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval import (
    WorkbenchRagEvalPromotionApplyResult,
    WorkbenchRagEvalPromotionStatus,
)
from src.contexts.knowledge_workbench.rag_eval.application.policies.promoted_question_runtime_embedding_text_builder import (
    PromotedQuestionRuntimeEmbeddingTextBuilder,
    append_question_once,
)
from src.contexts.knowledge_workbench.rag_eval.application.ports.workbench_rag_eval_repository_port import (
    WorkbenchRagEvalRepositoryPort,
)


class WorkbenchRagEvalPromotionNotFoundError(LookupError):
    pass


class WorkbenchRagEvalPromotionConflictError(RuntimeError):
    pass


class WorkbenchRagEvalPromotionEmbeddingError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ApplyWorkbenchRagEvalPromotion:
    rag_eval_repository: WorkbenchRagEvalRepositoryPort
    embedding_generation_port: EmbeddingGenerationPort
    embedding_model_id: str
    embedding_dimensions: int
    embedding_text_builder: PromotedQuestionRuntimeEmbeddingTextBuilder

    async def execute(
        self,
        *,
        project_id: str,
        promotion_id: str,
        applied_at: datetime,
    ) -> WorkbenchRagEvalPromotionApplyResult:
        project_id = _require_text(project_id, "project_id")
        promotion_id = _require_text(promotion_id, "promotion_id")
        if not self.embedding_model_id.strip():
            raise ValueError("embedding_model_id must be non-empty")
        if self.embedding_dimensions < 1:
            raise ValueError("embedding_dimensions must be positive")

        candidate = await self.rag_eval_repository.get_promotion_candidate(
            project_id=project_id,
            promotion_id=promotion_id,
        )
        if candidate is None:
            raise WorkbenchRagEvalPromotionNotFoundError(
                "Promotion candidate not found"
            )
        if candidate.status is WorkbenchRagEvalPromotionStatus.APPLIED:
            raise WorkbenchRagEvalPromotionConflictError(
                "Promotion candidate is already applied"
            )
        if candidate.status not in (
            WorkbenchRagEvalPromotionStatus.CANDIDATE,
            WorkbenchRagEvalPromotionStatus.ACCEPTED,
        ):
            raise WorkbenchRagEvalPromotionConflictError(
                f"Promotion candidate status cannot be applied: {candidate.status.value}"
            )

        target = await self.rag_eval_repository.get_promotion_application_target(
            project_id=project_id,
            promotion_id=promotion_id,
        )
        if target is None:
            raise WorkbenchRagEvalPromotionNotFoundError("Promotion target not found")

        updated_questions = append_question_once(
            possible_questions=target.runtime_possible_questions,
            question=target.question,
        )
        embedding_text = self.embedding_text_builder.build(
            claim=target.claim,
            possible_questions=updated_questions,
            exclusion_scope=target.exclusion_scope,
            existing_embedding_text=target.existing_embedding_text,
        )
        embedding = await self._embed(embedding_text.text)

        return await self.rag_eval_repository.apply_promotion_candidate(
            project_id=project_id,
            promotion_id=promotion_id,
            embedding_model_id=self.embedding_model_id,
            dimensions=self.embedding_dimensions,
            embedding=embedding,
            embedding_text=embedding_text.text,
            embedding_text_hash=embedding_text.text_hash,
            applied_at=applied_at,
        )

    async def _embed(self, text: str) -> tuple[float, ...]:
        try:
            result = await self.embedding_generation_port.embed(
                EmbeddingGenerationRequest(
                    texts=(text,),
                    model_id=self.embedding_model_id,
                    expected_dimensions=self.embedding_dimensions,
                    task="retrieval.passage",
                )
            )
        except Exception as exc:
            raise WorkbenchRagEvalPromotionEmbeddingError(
                "Failed to generate promotion embedding"
            ) from exc

        if len(result.embeddings) != 1:
            raise WorkbenchRagEvalPromotionEmbeddingError(
                "Promotion embedding generation returned unexpected vector count"
            )
        vector = result.embeddings[0]
        _validate_embedding(vector, self.embedding_dimensions)
        return tuple(float(value) for value in vector)


def _validate_embedding(vector: Sequence[float], dimensions: int) -> None:
    if len(vector) != dimensions:
        raise WorkbenchRagEvalPromotionEmbeddingError(
            "Promotion embedding has unexpected dimensions"
        )
    for index, value in enumerate(vector):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise WorkbenchRagEvalPromotionEmbeddingError(
                f"Promotion embedding[{index}] must be numeric"
            )


def _require_text(value: str, field_name: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{field_name} must be non-empty")
    return stripped
