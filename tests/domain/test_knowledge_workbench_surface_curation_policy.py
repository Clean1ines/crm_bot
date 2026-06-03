from __future__ import annotations

from src.domain.project_plane.knowledge_workbench import CurationChangeOperation
from src.domain.project_plane.knowledge_workbench.curation import (
    DRAFT_SURFACE_CURATION_OPERATIONS,
    curation_operation_is_destructive,
    curation_operation_requires_relation_target,
    ensure_curation_operation_targets_draft_surface,
)


def test_surface_curation_policy_keeps_only_draft_surface_operations() -> None:
    assert DRAFT_SURFACE_CURATION_OPERATIONS == {
        CurationChangeOperation.EDIT_QUESTION,
        CurationChangeOperation.EDIT_ANSWER,
        CurationChangeOperation.EDIT_SCOPE,
        CurationChangeOperation.MERGE,
        CurationChangeOperation.DELETE,
        CurationChangeOperation.REJECT,
        CurationChangeOperation.RESTORE,
        CurationChangeOperation.ADD_VARIANT,
        CurationChangeOperation.REMOVE_VARIANT,
    }

    for operation in DRAFT_SURFACE_CURATION_OPERATIONS:
        ensure_curation_operation_targets_draft_surface(operation)


def test_surface_curation_policy_keeps_runtime_and_eval_jobs_out_of_draft_curation() -> (
    None
):
    operation_values = {operation.value for operation in CurationChangeOperation}

    assert "publish_entry" not in operation_values
    assert "unpublish_entry" not in operation_values
    assert "hide_entry" not in operation_values
    assert "rebuild_embedding" not in operation_values
    assert "rerun_eval" not in operation_values


def test_surface_curation_policy_marks_merge_and_destructive_operations() -> None:
    assert curation_operation_requires_relation_target(CurationChangeOperation.MERGE)
    assert not curation_operation_requires_relation_target(
        CurationChangeOperation.EDIT_ANSWER
    )

    assert curation_operation_is_destructive(CurationChangeOperation.DELETE)
    assert curation_operation_is_destructive(CurationChangeOperation.REJECT)
    assert not curation_operation_is_destructive(CurationChangeOperation.RESTORE)
