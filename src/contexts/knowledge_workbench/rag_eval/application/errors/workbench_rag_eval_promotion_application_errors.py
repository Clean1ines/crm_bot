from __future__ import annotations

from enum import StrEnum


class WorkbenchRagEvalPromotionConflictCode(StrEnum):
    NON_APPROVED_CANDIDATE = "non_approved_candidate"
    ACTIVE_REVISION = "active_revision"
    STALE_RUNTIME_SNAPSHOT = "stale_runtime_snapshot"
    ALIAS_LIMIT_EXCEEDED = "alias_limit_exceeded"
    TARGET_NOT_ACTIVE = "target_not_active"
    TARGET_NOT_PUBLISHED = "target_not_published"
    MIXED_SOURCE_RUNS = "mixed_source_runs"
    ALREADY_APPLIED_BY_OTHER_REVISION = "already_applied_by_other_revision"
    DUPLICATE_SELECTED_ALIAS = "duplicate_selected_alias"
    EXISTING_ALIAS = "existing_alias"
    PERSISTENCE_CONFLICT = "persistence_conflict"


class WorkbenchRagEvalPromotionNotFoundError(LookupError):
    pass


class WorkbenchRagEvalPromotionConflictError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: WorkbenchRagEvalPromotionConflictCode = (
            WorkbenchRagEvalPromotionConflictCode.PERSISTENCE_CONFLICT
        ),
        promotion_ids: tuple[str, ...] = (),
        runtime_entry_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.promotion_ids = promotion_ids
        self.runtime_entry_id = runtime_entry_id


class WorkbenchRagEvalPromotionEmbeddingError(RuntimeError):
    pass
