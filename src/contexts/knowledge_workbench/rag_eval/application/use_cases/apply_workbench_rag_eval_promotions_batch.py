from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from uuid import uuid4

from src.contexts.embedding_runtime.application.ports.embedding_generation_port import (
    EmbeddingGenerationPort,
    EmbeddingGenerationRequest,
)
from src.contexts.knowledge_workbench.rag_eval.application.errors.workbench_rag_eval_promotion_application_errors import (
    WorkbenchRagEvalPromotionConflictCode,
    WorkbenchRagEvalPromotionConflictError,
    WorkbenchRagEvalPromotionEmbeddingError,
    WorkbenchRagEvalPromotionNotFoundError,
)
from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval import (
    WorkbenchRagEvalPromotionApplicationTarget,
    WorkbenchRagEvalPromotionStatus,
)
from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval_embedding_revision import (
    WORKBENCH_RUNTIME_EMBEDDING_DIMENSIONS,
    WorkbenchRagEvalEmbeddingRevision,
    WorkbenchRagEvalEmbeddingRevisionReadModel,
    WorkbenchRagEvalEmbeddingRevisionStatus,
    WorkbenchRagEvalPromotionApplicationClaimDecisionCode,
    WorkbenchRagEvalPromotionApplicationError,
    WorkbenchRagEvalPromotionApplicationResult,
    WorkbenchRagEvalPromotionRevisionResult,
    stable_embedding_revision_id,
    stable_promotion_application_key,
    stable_runtime_snapshot_hash,
)
from src.contexts.knowledge_workbench.rag_eval.application.policies.promoted_question_runtime_embedding_text_builder import (
    PromotedQuestionRuntimeEmbeddingTextBuilder,
)
from src.contexts.knowledge_workbench.rag_eval.application.policies.workbench_rag_eval_promotion_application_policy import (
    WorkbenchRagEvalPromotionApplicationConflictCode,
    WorkbenchRagEvalPromotionApplicationDecisionCode,
    WorkbenchRagEvalPromotionApplicationPolicy,
    WorkbenchRagEvalPromotionApplicationPolicyConflictError,
)
from src.contexts.knowledge_workbench.rag_eval.application.ports.workbench_rag_eval_repository_port import (
    WorkbenchRagEvalRepositoryPort,
)


_DEFAULT_APPLICATION_LEASE_SECONDS = 300


def _new_lease_owner() -> str:
    return f"rag-eval-promotion-application:{uuid4()}"


@dataclass(slots=True)
class ApplyWorkbenchRagEvalPromotionsBatch:
    rag_eval_repository: WorkbenchRagEvalRepositoryPort
    embedding_generation_port: EmbeddingGenerationPort
    embedding_model_id: str
    embedding_dimensions: int
    embedding_text_builder: PromotedQuestionRuntimeEmbeddingTextBuilder
    application_policy: WorkbenchRagEvalPromotionApplicationPolicy
    application_lease_seconds: int = _DEFAULT_APPLICATION_LEASE_SECONDS
    lease_owner_factory: Callable[[], str] = field(default=_new_lease_owner)

    def __post_init__(self) -> None:
        if self.embedding_dimensions != WORKBENCH_RUNTIME_EMBEDDING_DIMENSIONS:
            raise ValueError(
                "RAG Eval promotion application requires embedding_dimensions = "
                f"{WORKBENCH_RUNTIME_EMBEDDING_DIMENSIONS}"
            )
        if (
            isinstance(self.application_lease_seconds, bool)
            or not isinstance(self.application_lease_seconds, int)
            or self.application_lease_seconds <= 0
        ):
            raise ValueError("application_lease_seconds must be > 0")

    async def execute(
        self,
        *,
        project_id: str,
        mode: str,
        promotion_ids: Sequence[str],
        run_id: str | None,
        applied_at: datetime,
    ) -> WorkbenchRagEvalPromotionApplicationResult:
        normalized_mode = mode.strip().lower()
        requested_ids = tuple(
            dict.fromkeys(item.strip() for item in promotion_ids if item.strip())
        )
        targets = await self._load_targets(
            project_id=project_id,
            mode=normalized_mode,
            promotion_ids=requested_ids,
            run_id=run_id,
        )
        if normalized_mode == "selected":
            found_ids = {target.promotion_id for target in targets}
            missing_ids = tuple(
                promotion_id
                for promotion_id in requested_ids
                if promotion_id not in found_ids
            )
            if missing_ids:
                raise WorkbenchRagEvalPromotionNotFoundError(
                    "Promotion candidates not found: " + ", ".join(missing_ids)
                )

        requested_count = (
            len(requested_ids) if normalized_mode == "selected" else len(targets)
        )
        errors: list[WorkbenchRagEvalPromotionApplicationError] = []
        revisions: list[WorkbenchRagEvalPromotionRevisionResult] = []
        embedding_recalculation_count = 0

        eligible_targets: list[WorkbenchRagEvalPromotionApplicationTarget] = []
        for target in targets:
            if target.status in {
                WorkbenchRagEvalPromotionStatus.APPROVED,
                WorkbenchRagEvalPromotionStatus.APPLIED,
            }:
                eligible_targets.append(target)
                continue
            errors.append(
                WorkbenchRagEvalPromotionApplicationError(
                    code=WorkbenchRagEvalPromotionConflictCode.NON_APPROVED_CANDIDATE.value,
                    message=(
                        f"promotion {target.promotion_id} cannot apply status "
                        f"{target.status.value}"
                    ),
                    promotion_ids=(target.promotion_id,),
                    runtime_entry_id=target.target_runtime_entry_id,
                )
            )

        grouped: dict[str, list[WorkbenchRagEvalPromotionApplicationTarget]] = (
            defaultdict(list)
        )
        for target in eligible_targets:
            grouped[target.target_runtime_entry_id].append(target)

        for runtime_entry_id in sorted(grouped):
            group = tuple(
                sorted(
                    grouped[runtime_entry_id],
                    key=lambda item: item.promotion_id,
                )
            )
            group_ids = tuple(item.promotion_id for item in group)
            group_statuses = {item.status for item in group}

            if group_statuses == {WorkbenchRagEvalPromotionStatus.APPLIED}:
                idempotent = await self._load_idempotent_revision(
                    project_id=project_id,
                    runtime_entry_id=runtime_entry_id,
                    group=group,
                )
                if idempotent is not None:
                    revisions.append(idempotent)
                    continue
                errors.append(
                    WorkbenchRagEvalPromotionApplicationError(
                        code=(
                            WorkbenchRagEvalPromotionConflictCode.ALREADY_APPLIED_BY_OTHER_REVISION.value
                        ),
                        message=(
                            "promotions are already APPLIED by another or non-pending "
                            "revision"
                        ),
                        promotion_ids=group_ids,
                        runtime_entry_id=runtime_entry_id,
                    )
                )
                continue

            if WorkbenchRagEvalPromotionStatus.APPLIED in group_statuses:
                errors.append(
                    WorkbenchRagEvalPromotionApplicationError(
                        code=(
                            WorkbenchRagEvalPromotionConflictCode.ALREADY_APPLIED_BY_OTHER_REVISION.value
                        ),
                        message=(
                            "APPROVED and APPLIED promotions cannot be mixed in one "
                            "new mutation"
                        ),
                        promotion_ids=group_ids,
                        runtime_entry_id=runtime_entry_id,
                    )
                )
                continue

            try:
                snapshot = (
                    await self.rag_eval_repository.load_promotion_application_group(
                        project_id=project_id,
                        promotion_ids=group_ids,
                        target_runtime_entry_id=runtime_entry_id,
                        embedding_model_id=self.embedding_model_id,
                    )
                )
                if snapshot is None:
                    raise WorkbenchRagEvalPromotionNotFoundError(
                        f"promotion application target {runtime_entry_id} not found"
                    )
                decision = self.application_policy.decide(snapshot)
            except WorkbenchRagEvalPromotionApplicationPolicyConflictError as exc:
                errors.append(
                    WorkbenchRagEvalPromotionApplicationError(
                        code=_application_conflict_code(exc.code).value,
                        message=str(exc),
                        promotion_ids=exc.promotion_ids or group_ids,
                        runtime_entry_id=runtime_entry_id,
                    )
                )
                continue
            except WorkbenchRagEvalPromotionConflictError as exc:
                errors.append(_error_from_conflict(exc, group_ids, runtime_entry_id))
                continue
            except WorkbenchRagEvalPromotionNotFoundError as exc:
                errors.append(
                    WorkbenchRagEvalPromotionApplicationError(
                        code="not_found",
                        message=str(exc),
                        promotion_ids=group_ids,
                        runtime_entry_id=runtime_entry_id,
                    )
                )
                continue

            for skipped in decision.skipped_candidates:
                code = (
                    WorkbenchRagEvalPromotionConflictCode.EXISTING_ALIAS
                    if skipped.code
                    is WorkbenchRagEvalPromotionApplicationDecisionCode.EXISTING_ALIAS
                    else WorkbenchRagEvalPromotionConflictCode.DUPLICATE_SELECTED_ALIAS
                )
                errors.append(
                    WorkbenchRagEvalPromotionApplicationError(
                        code=code.value,
                        message=skipped.message,
                        promotion_ids=(skipped.promotion_id,),
                        runtime_entry_id=runtime_entry_id,
                    )
                )

            if not decision.should_apply:
                continue

            applicable_snapshot = replace(
                snapshot,
                candidates=decision.applicable_candidates,
            )
            applicable_ids = tuple(
                candidate.promotion_id for candidate in decision.applicable_candidates
            )
            application_key = stable_promotion_application_key(
                project_id=project_id,
                runtime_entry_id=runtime_entry_id,
                source_rag_eval_run_id=applicable_snapshot.source_rag_eval_run_id,
                promotion_ids=applicable_ids,
                previous_runtime_hash=snapshot.runtime_hash,
            )
            lease_owner = self.lease_owner_factory()
            lease_expires_at = applied_at + timedelta(
                seconds=self.application_lease_seconds
            )
            try:
                claim_decision = (
                    await self.rag_eval_repository.claim_promotion_application(
                        application_key=application_key,
                        project_id=project_id,
                        runtime_entry_id=runtime_entry_id,
                        source_rag_eval_run_id=(
                            applicable_snapshot.source_rag_eval_run_id
                        ),
                        promotion_ids=applicable_ids,
                        previous_runtime_hash=snapshot.runtime_hash,
                        lease_owner=lease_owner,
                        now=applied_at,
                        lease_expires_at=lease_expires_at,
                    )
                )
            except WorkbenchRagEvalPromotionConflictError as exc:
                errors.append(
                    _error_from_conflict(exc, applicable_ids, runtime_entry_id)
                )
                continue

            if (
                claim_decision.code
                is WorkbenchRagEvalPromotionApplicationClaimDecisionCode.ALREADY_COMPLETED
            ):
                completed_revision = claim_decision.revision
                if completed_revision is None:
                    raise RuntimeError(
                        "ALREADY_COMPLETED claim decision is missing revision"
                    )
                revisions.append(_idempotent_revision_result(completed_revision))
                continue
            if (
                claim_decision.code
                is WorkbenchRagEvalPromotionApplicationClaimDecisionCode.IN_PROGRESS
            ):
                errors.append(
                    WorkbenchRagEvalPromotionApplicationError(
                        code=(
                            WorkbenchRagEvalPromotionConflictCode.APPLICATION_IN_PROGRESS.value
                        ),
                        message="promotion application is already in progress",
                        promotion_ids=applicable_ids,
                        runtime_entry_id=runtime_entry_id,
                    )
                )
                continue
            if (
                claim_decision.code
                is WorkbenchRagEvalPromotionApplicationClaimDecisionCode.CONFLICTING_ACTIVE_GROUP
            ):
                errors.append(
                    WorkbenchRagEvalPromotionApplicationError(
                        code=(
                            WorkbenchRagEvalPromotionConflictCode.CONFLICTING_ACTIVE_APPLICATION.value
                        ),
                        message=(
                            "another promotion application group is active for this "
                            "runtime entry"
                        ),
                        promotion_ids=applicable_ids,
                        runtime_entry_id=runtime_entry_id,
                    )
                )
                continue
            if claim_decision.code not in {
                WorkbenchRagEvalPromotionApplicationClaimDecisionCode.ACQUIRED,
                WorkbenchRagEvalPromotionApplicationClaimDecisionCode.RECOVERED_EXPIRED_LEASE,
            }:
                raise RuntimeError(
                    f"unsupported application claim decision {claim_decision.code}"
                )

            built = self.embedding_text_builder.build(
                claim=snapshot.claim,
                possible_questions=decision.new_possible_questions,
                exclusion_scope=snapshot.exclusion_scope,
                existing_embedding_text=snapshot.embedding_text,
            )
            try:
                # one grouped embedding generation; persisted claim owner only
                embedding = await self._embed(built.text)
            except WorkbenchRagEvalPromotionEmbeddingError as exc:
                cleanup_error = await self._fail_claim(
                    application_key=application_key,
                    lease_owner=lease_owner,
                    failed_at=applied_at,
                    promotion_ids=applicable_ids,
                    runtime_entry_id=runtime_entry_id,
                )
                errors.append(
                    cleanup_error
                    or WorkbenchRagEvalPromotionApplicationError(
                        code="embedding_failed",
                        message=str(exc),
                        promotion_ids=applicable_ids,
                        runtime_entry_id=runtime_entry_id,
                    )
                )
                continue
            embedding_recalculation_count += 1

            new_runtime_hash = stable_runtime_snapshot_hash(
                possible_questions=decision.new_possible_questions,
                embedding_text=built.text,
                embedding=embedding,
                embedding_model_id=self.embedding_model_id,
                embedding_dimensions=self.embedding_dimensions,
            )
            revision = WorkbenchRagEvalEmbeddingRevision(
                revision_id=stable_embedding_revision_id(
                    project_id=project_id,
                    runtime_entry_id=runtime_entry_id,
                    source_rag_eval_run_id=(applicable_snapshot.source_rag_eval_run_id),
                    promotion_ids=applicable_ids,
                    previous_runtime_hash=snapshot.runtime_hash,
                ),
                project_id=project_id,
                runtime_entry_id=runtime_entry_id,
                source_rag_eval_run_id=(applicable_snapshot.source_rag_eval_run_id),
                promotion_ids=applicable_ids,
                status=(WorkbenchRagEvalEmbeddingRevisionStatus.PENDING_VERIFICATION),
                previous_embedding_text=snapshot.embedding_text,
                new_embedding_text=built.text,
                previous_embedding=snapshot.embedding,
                new_embedding=embedding,
                previous_promoted_questions=snapshot.possible_questions,
                new_promoted_questions=decision.new_possible_questions,
                embedding_model_id=self.embedding_model_id,
                embedding_dimensions=self.embedding_dimensions,
                previous_runtime_hash=snapshot.runtime_hash,
                new_runtime_hash=new_runtime_hash,
                created_at=applied_at,
                accepted_at=None,
                regression_failed_at=None,
                rolled_back_at=None,
            )
            try:
                persisted = await self.rag_eval_repository.persist_promotion_application_revision(
                    snapshot=applicable_snapshot,
                    revision=revision,
                    application_key=application_key,
                    lease_owner=lease_owner,
                )
            except WorkbenchRagEvalPromotionConflictError as exc:
                cleanup_error = await self._fail_claim(
                    application_key=application_key,
                    lease_owner=lease_owner,
                    failed_at=applied_at,
                    promotion_ids=applicable_ids,
                    runtime_entry_id=runtime_entry_id,
                )
                errors.append(
                    cleanup_error
                    or _error_from_conflict(
                        exc,
                        applicable_ids,
                        runtime_entry_id,
                    )
                )
                continue
            except Exception:
                await self._fail_claim(
                    application_key=application_key,
                    lease_owner=lease_owner,
                    failed_at=applied_at,
                    promotion_ids=applicable_ids,
                    runtime_entry_id=runtime_entry_id,
                )
                raise

            try:
                await self.rag_eval_repository.complete_promotion_application_claim(
                    application_key=application_key,
                    lease_owner=lease_owner,
                    revision_id=persisted.revision_id,
                    completed_at=applied_at,
                )
            except WorkbenchRagEvalPromotionConflictError as exc:
                errors.append(
                    _error_from_conflict(exc, applicable_ids, runtime_entry_id)
                )
                continue

            revisions.append(
                WorkbenchRagEvalPromotionRevisionResult(
                    revision_id=persisted.revision_id,
                    runtime_entry_id=persisted.runtime_entry_id,
                    source_rag_eval_run_id=persisted.source_rag_eval_run_id,
                    status=persisted.status,
                    promotion_ids=persisted.promotion_ids,
                    idempotent=False,
                )
            )

        applied_count = sum(len(revision.promotion_ids) for revision in revisions)
        return WorkbenchRagEvalPromotionApplicationResult(
            requested_count=requested_count,
            applied_count=applied_count,
            skipped_count=max(0, requested_count - applied_count),
            embedding_recalculation_count=embedding_recalculation_count,
            revisions=tuple(revisions),
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
            if not promotion_ids:
                raise ValueError("promotion_ids must be non-empty for selected mode")
            return await self.rag_eval_repository.list_promotion_application_targets_for_ids(
                project_id=project_id,
                promotion_ids=promotion_ids,
            )
        if mode == "all_candidates_for_run":
            if run_id is None or not run_id.strip():
                raise ValueError(
                    "run_id must be non-empty for all_candidates_for_run mode"
                )
            return await self.rag_eval_repository.list_promotion_application_targets_for_run(
                project_id=project_id,
                run_id=run_id,
            )
        raise ValueError("mode must be selected or all_candidates_for_run")

    async def _load_idempotent_revision(
        self,
        *,
        project_id: str,
        runtime_entry_id: str,
        group: tuple[WorkbenchRagEvalPromotionApplicationTarget, ...],
    ) -> WorkbenchRagEvalPromotionRevisionResult | None:
        run_ids = {target.run_id for target in group}
        if len(run_ids) != 1:
            return None
        promotion_ids = tuple(target.promotion_id for target in group)
        revision = await self.rag_eval_repository.find_pending_revision_for_promotions(
            project_id=project_id,
            runtime_entry_id=runtime_entry_id,
            source_rag_eval_run_id=next(iter(run_ids)),
            promotion_ids=promotion_ids,
        )
        if revision is None:
            return None
        return _idempotent_revision_result(revision)

    async def _fail_claim(
        self,
        *,
        application_key: str,
        lease_owner: str,
        failed_at: datetime,
        promotion_ids: tuple[str, ...],
        runtime_entry_id: str,
    ) -> WorkbenchRagEvalPromotionApplicationError | None:
        try:
            await self.rag_eval_repository.fail_promotion_application_claim(
                application_key=application_key,
                lease_owner=lease_owner,
                failed_at=failed_at,
            )
        except WorkbenchRagEvalPromotionConflictError as exc:
            return _error_from_conflict(exc, promotion_ids, runtime_entry_id)
        return None

    async def _embed(self, text: str) -> tuple[float, ...]:
        try:
            result = await self.embedding_generation_port.embed(
                EmbeddingGenerationRequest(
                    texts=(text,),
                    model_id=self.embedding_model_id,
                    expected_dimensions=WORKBENCH_RUNTIME_EMBEDDING_DIMENSIONS,
                    task="retrieval.passage",
                )
            )
        except Exception as exc:
            raise WorkbenchRagEvalPromotionEmbeddingError(
                "Embedding provider failed"
            ) from exc
        if result.model_id != self.embedding_model_id:
            raise WorkbenchRagEvalPromotionEmbeddingError(
                "Embedding provider returned unexpected model"
            )
        if result.dimensions != WORKBENCH_RUNTIME_EMBEDDING_DIMENSIONS:
            raise WorkbenchRagEvalPromotionEmbeddingError(
                "Embedding provider returned unexpected dimensions"
            )
        if len(result.embeddings) != 1:
            raise WorkbenchRagEvalPromotionEmbeddingError(
                "Embedding provider must return exactly one vector"
            )
        embedding = tuple(float(value) for value in result.embeddings[0])
        if len(embedding) != WORKBENCH_RUNTIME_EMBEDDING_DIMENSIONS:
            raise WorkbenchRagEvalPromotionEmbeddingError(
                "Embedding vector dimensions mismatch"
            )
        return embedding


def _idempotent_revision_result(
    revision: WorkbenchRagEvalEmbeddingRevisionReadModel,
) -> WorkbenchRagEvalPromotionRevisionResult:
    return WorkbenchRagEvalPromotionRevisionResult(
        revision_id=revision.revision_id,
        runtime_entry_id=revision.runtime_entry_id,
        source_rag_eval_run_id=revision.source_rag_eval_run_id,
        status=revision.status,
        promotion_ids=revision.promotion_ids,
        idempotent=True,
    )


def _application_conflict_code(
    code: WorkbenchRagEvalPromotionApplicationConflictCode,
) -> WorkbenchRagEvalPromotionConflictCode:
    mapping = {
        WorkbenchRagEvalPromotionApplicationConflictCode.NON_APPROVED_CANDIDATE: (
            WorkbenchRagEvalPromotionConflictCode.NON_APPROVED_CANDIDATE
        ),
        WorkbenchRagEvalPromotionApplicationConflictCode.SUPERSEDED_CANDIDATE: (
            WorkbenchRagEvalPromotionConflictCode.NON_APPROVED_CANDIDATE
        ),
        WorkbenchRagEvalPromotionApplicationConflictCode.INACTIVE_TARGET: (
            WorkbenchRagEvalPromotionConflictCode.TARGET_NOT_ACTIVE
        ),
        WorkbenchRagEvalPromotionApplicationConflictCode.UNPUBLISHED_TARGET: (
            WorkbenchRagEvalPromotionConflictCode.TARGET_NOT_PUBLISHED
        ),
        WorkbenchRagEvalPromotionApplicationConflictCode.ACTIVE_REVISION: (
            WorkbenchRagEvalPromotionConflictCode.ACTIVE_REVISION
        ),
        WorkbenchRagEvalPromotionApplicationConflictCode.ALIAS_LIMIT_EXCEEDED: (
            WorkbenchRagEvalPromotionConflictCode.ALIAS_LIMIT_EXCEEDED
        ),
        WorkbenchRagEvalPromotionApplicationConflictCode.MIXED_SOURCE_RUNS: (
            WorkbenchRagEvalPromotionConflictCode.MIXED_SOURCE_RUNS
        ),
        WorkbenchRagEvalPromotionApplicationConflictCode.TARGET_FACT_MISMATCH: (
            WorkbenchRagEvalPromotionConflictCode.STALE_RUNTIME_SNAPSHOT
        ),
        WorkbenchRagEvalPromotionApplicationConflictCode.DUPLICATE_PROMOTION_ID: (
            WorkbenchRagEvalPromotionConflictCode.PERSISTENCE_CONFLICT
        ),
    }
    return mapping[code]


def _error_from_conflict(
    exc: WorkbenchRagEvalPromotionConflictError,
    promotion_ids: tuple[str, ...],
    runtime_entry_id: str,
) -> WorkbenchRagEvalPromotionApplicationError:
    return WorkbenchRagEvalPromotionApplicationError(
        code=exc.code.value,
        message=str(exc),
        promotion_ids=exc.promotion_ids or promotion_ids,
        runtime_entry_id=exc.runtime_entry_id or runtime_entry_id,
    )
