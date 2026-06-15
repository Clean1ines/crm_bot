from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from src.contexts.embedding_runtime.application.ports.embedding_generation_port import (
    EmbeddingGenerationPort,
    EmbeddingGenerationRequest,
)
from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval import (
    WorkbenchRagEvalPromotionApplicationTarget,
    WorkbenchRagEvalPromotionBatchApplyResult,
    WorkbenchRagEvalPromotionStatus,
)
from src.contexts.knowledge_workbench.rag_eval.application.policies.promoted_question_runtime_embedding_text_builder import (
    PromotedQuestionRuntimeEmbeddingTextBuilder,
)
from src.contexts.knowledge_workbench.rag_eval.application.ports.workbench_rag_eval_repository_port import (
    WorkbenchRagEvalRepositoryPort,
)
from src.contexts.knowledge_workbench.rag_eval.application.use_cases.apply_workbench_rag_eval_promotion import (
    WorkbenchRagEvalPromotionEmbeddingError,
    WorkbenchRagEvalPromotionNotFoundError,
)


@dataclass(frozen=True, slots=True)
class ApplyWorkbenchRagEvalPromotionsBatch:
    rag_eval_repository: WorkbenchRagEvalRepositoryPort
    embedding_generation_port: EmbeddingGenerationPort
    embedding_model_id: str
    embedding_dimensions: int
    embedding_text_builder: PromotedQuestionRuntimeEmbeddingTextBuilder

    async def execute(
        self,
        *,
        project_id: str,
        mode: str,
        promotion_ids: tuple[str, ...],
        run_id: str | None,
        applied_at: datetime,
    ) -> WorkbenchRagEvalPromotionBatchApplyResult:
        project_id = _require_text(project_id, "project_id")
        mode = _require_text(mode, "mode")
        if mode not in ("selected", "all_candidates_for_run"):
            raise ValueError("mode must be selected or all_candidates_for_run")
        if not self.embedding_model_id.strip():
            raise ValueError("embedding_model_id must be non-empty")
        if self.embedding_dimensions < 1:
            raise ValueError("embedding_dimensions must be positive")

        targets = await self._load_targets(
            project_id=project_id,
            mode=mode,
            promotion_ids=promotion_ids,
            run_id=run_id,
        )
        requested_count = len(promotion_ids) if mode == "selected" else len(targets)

        eligible: list[WorkbenchRagEvalPromotionApplicationTarget] = []
        skipped_count = 0
        errors: list[str] = []

        for target in targets:
            if target.status is WorkbenchRagEvalPromotionStatus.APPLIED:
                skipped_count += 1
                continue
            if target.status not in (
                WorkbenchRagEvalPromotionStatus.CANDIDATE,
                WorkbenchRagEvalPromotionStatus.ACCEPTED,
            ):
                skipped_count += 1
                errors.append(
                    f"{target.promotion_id}: cannot apply status {target.status.value}"
                )
                continue
            eligible.append(target)

        groups = _group_by_runtime_entry(eligible)
        applied_count = 0
        embedding_recalculation_count = 0

        for group in groups:
            base = group[0]
            questions = tuple(target.question for target in group)
            updated_questions = _append_questions_once(
                base.runtime_possible_questions,
                questions,
            )
            embedding_text = self.embedding_text_builder.build(
                claim=base.claim,
                possible_questions=updated_questions,
                exclusion_scope=base.exclusion_scope,
                existing_embedding_text=base.existing_embedding_text,
            )
            embedding = await self._embed(embedding_text.text)
            results = (
                await self.rag_eval_repository.apply_promotion_candidates_for_target(
                    project_id=project_id,
                    promotion_ids=tuple(target.promotion_id for target in group),
                    target_runtime_entry_id=base.target_runtime_entry_id,
                    embedding_model_id=self.embedding_model_id,
                    dimensions=self.embedding_dimensions,
                    embedding=embedding,
                    embedding_text=embedding_text.text,
                    embedding_text_hash=embedding_text.text_hash,
                    applied_at=applied_at,
                )
            )
            applied_count += len(results)
            if results:
                embedding_recalculation_count += 1

        return WorkbenchRagEvalPromotionBatchApplyResult(
            requested_count=requested_count,
            applied_count=applied_count,
            skipped_count=skipped_count,
            embedding_recalculation_count=embedding_recalculation_count,
            errors=tuple(errors),
        )

    async def _load_targets(
        self,
        *,
        project_id: str,
        mode: str,
        promotion_ids: tuple[str, ...],
        run_id: str | None,
    ) -> tuple[WorkbenchRagEvalPromotionApplicationTarget, ...]:
        if mode == "selected":
            promotion_ids = _dedupe_ids(promotion_ids)
            if not promotion_ids:
                raise ValueError("promotion_ids must be non-empty for selected mode")
            targets = await self.rag_eval_repository.list_promotion_application_targets_for_ids(
                project_id=project_id,
                promotion_ids=promotion_ids,
            )
            found_ids = {target.promotion_id for target in targets}
            missing_ids = tuple(
                promotion_id
                for promotion_id in promotion_ids
                if promotion_id not in found_ids
            )
            if missing_ids:
                raise WorkbenchRagEvalPromotionNotFoundError(
                    "Promotion candidates not found"
                )
            return targets

        checked_run_id = _require_optional_run_id(run_id)
        return (
            await self.rag_eval_repository.list_promotion_application_targets_for_run(
                project_id=project_id,
                run_id=checked_run_id,
            )
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
                "Failed to generate batch promotion embedding"
            ) from exc

        if len(result.embeddings) != 1:
            raise WorkbenchRagEvalPromotionEmbeddingError(
                "Batch promotion embedding generation returned unexpected vector count"
            )
        vector = result.embeddings[0]
        _validate_embedding(vector, self.embedding_dimensions)
        return tuple(float(value) for value in vector)


def _group_by_runtime_entry(
    targets: list[WorkbenchRagEvalPromotionApplicationTarget],
) -> tuple[tuple[WorkbenchRagEvalPromotionApplicationTarget, ...], ...]:
    grouped: dict[str, list[WorkbenchRagEvalPromotionApplicationTarget]] = {}
    order: list[str] = []
    for target in targets:
        key = target.target_runtime_entry_id
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append(target)
    return tuple(tuple(grouped[key]) for key in order)


def _append_questions_once(
    existing: tuple[str, ...],
    additions: tuple[str, ...],
) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for question in (*existing, *additions):
        stripped = question.strip()
        if not stripped:
            continue
        normalized = " ".join(stripped.casefold().split())
        if normalized in seen:
            continue
        seen.add(normalized)
        result.append(stripped)
    return tuple(result)


def _dedupe_ids(values: tuple[str, ...]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        stripped = _require_text(value, "promotion_id")
        if stripped in seen:
            continue
        seen.add(stripped)
        result.append(stripped)
    return tuple(result)


def _validate_embedding(vector: Sequence[float], dimensions: int) -> None:
    if len(vector) != dimensions:
        raise WorkbenchRagEvalPromotionEmbeddingError(
            "Batch promotion embedding has unexpected dimensions"
        )
    for index, value in enumerate(vector):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise WorkbenchRagEvalPromotionEmbeddingError(
                f"Batch promotion embedding[{index}] must be numeric"
            )


def _require_optional_run_id(value: str | None) -> str:
    if value is None:
        raise ValueError("run_id must be provided for all_candidates_for_run mode")
    return _require_text(value, "run_id")


def _require_text(value: str, field_name: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{field_name} must be non-empty")
    return stripped
