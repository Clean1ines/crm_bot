from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalEventType,
    KnowledgeExtractionCanonicalPhase,
)
from src.contexts.knowledge_workbench.observability.application.projectors.draft_claim_cluster_frontend_workflow_event_projector import (
    DraftClaimClusterFrontendWorkflowEventProjector,
)
from src.contexts.workflow_runtime.domain.entities.workflow_event import WorkflowEvent
from src.contexts.workflow_runtime.domain.value_objects.workflow_event_id import (
    WorkflowEventId,
)

_CLUSTERS_BUILT_PAYLOAD_KEYS = frozenset(
    {
        "workflow_run_id",
        "candidate_edge_count",
        "group_count",
        "batch_count",
        "scheduled_work_item_count",
        "semantic_meaning",
        "draft_claim_cluster_rows",
    }
)


def _now() -> datetime:
    return datetime(2026, 6, 21, 12, 0, tzinfo=timezone.utc)


def _workflow_run_id() -> str:
    return "knowledge-extraction:source-document:project-1:abc"


def _canonical_payload() -> dict[str, object]:
    return {
        "workflow_run_id": _workflow_run_id(),
        "operation_key": "cluster_draft_claims",
        "canonical_phase": (
            KnowledgeExtractionCanonicalPhase.DRAFT_CLAIM_CLUSTERING.value
        ),
        "candidate_edge_count": 3,
        "group_count": 2,
        "batch_count": 2,
        "scheduled_work_item_count": 2,
        "semantic_meaning": "build hybrid draft claim compaction plan",
        "next_run_after": _now().isoformat(),
        "next_command_type": "PrepareDraftClaimCompactionDispatchBatch",
        "capacity_retry_at": _now().isoformat(),
    }


def _clusters_built_event(*, payload: dict[str, object] | None = None) -> WorkflowEvent:
    return WorkflowEvent(
        event_id=WorkflowEventId(
            "workflow-event:"
            f"{_workflow_run_id()}:"
            f"{KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_CLUSTERS_BUILT.value}:"
            "workflow-command:cluster:built"
        ),
        event_type=KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_CLUSTERS_BUILT.value,
        workflow_run_id=_workflow_run_id(),
        payload=payload or _canonical_payload(),
        occurred_at=_now(),
        sequence_number=71,
    )


def test_projects_clusters_built_to_versioned_envelope() -> None:
    event = _clusters_built_event()
    projected = DraftClaimClusterFrontendWorkflowEventProjector().project(event)

    assert projected is not None
    assert projected.projection_type == "workflow_draft_claim_clusters_built"
    assert projected.operation_key == "cluster_draft_claims"
    assert projected.canonical_phase == (
        KnowledgeExtractionCanonicalPhase.DRAFT_CLAIM_CLUSTERING.value
    )
    assert (
        projected.projection_event_id
        == f"frontend-workflow-event:{event.event_id.value}:"
        "workflow_draft_claim_clusters_built:v1"
    )


def test_ignores_unsupported_workflow_event() -> None:
    projected = DraftClaimClusterFrontendWorkflowEventProjector().project(
        WorkflowEvent(
            event_id=WorkflowEventId("workflow-event:unsupported"),
            event_type=KnowledgeExtractionCanonicalEventType.SOURCE_UNITS_CREATED.value,
            workflow_run_id=_workflow_run_id(),
            payload={"workflow_run_id": _workflow_run_id()},
            occurred_at=_now(),
            sequence_number=1,
        )
    )

    assert projected is None


@pytest.mark.parametrize("missing_key", ("operation_key", "canonical_phase"))
def test_requires_explicit_envelope_fields_in_payload(missing_key: str) -> None:
    payload = _canonical_payload()
    del payload[missing_key]

    with pytest.raises(ValueError, match=missing_key):
        DraftClaimClusterFrontendWorkflowEventProjector().project(
            _clusters_built_event(payload=payload)
        )


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    (
        ("operation_key", "wrong_operation"),
        ("canonical_phase", "WRONG_PHASE"),
    ),
)
def test_rejects_invalid_envelope_metadata(field: str, invalid_value: str) -> None:
    payload = _canonical_payload()
    payload[field] = invalid_value

    with pytest.raises(ValueError, match=field):
        DraftClaimClusterFrontendWorkflowEventProjector().project(
            _clusters_built_event(payload=payload)
        )


def test_projection_payload_is_allowlist_only() -> None:
    projected = DraftClaimClusterFrontendWorkflowEventProjector().project(
        _clusters_built_event()
    )

    assert projected is not None
    assert set(projected.payload) == _CLUSTERS_BUILT_PAYLOAD_KEYS
    assert projected.payload["group_count"] == 2
    assert projected.payload["batch_count"] == 2


def test_projection_exposes_cluster_row_availability() -> None:
    projected = DraftClaimClusterFrontendWorkflowEventProjector().project(
        _clusters_built_event()
    )

    assert projected is not None
    rows = projected.payload["draft_claim_cluster_rows"]
    assert isinstance(rows, dict)
    assert rows["surface_kind"] == "draft_claim_cluster_group"
    assert rows["availability"] == "available"
    assert rows["row_count"] == 2
    assert rows["batch_count"] == 2
    assert rows["parent_scope"] == {
        "workflow_run_id": _workflow_run_id(),
        "source_document_ref": "source-document:project-1:abc",
    }
    assert rows["targeted_read"] == {
        "kind": "draft_claim_clusters_by_workflow",
        "params": {
            "workflow_run_id": _workflow_run_id(),
            "include_batches": True,
        },
    }


def test_zero_groups_do_not_expose_available_cluster_rows() -> None:
    payload = _canonical_payload()
    payload["group_count"] = 0
    payload["batch_count"] = 0
    payload["scheduled_work_item_count"] = 0

    projected = DraftClaimClusterFrontendWorkflowEventProjector().project(
        _clusters_built_event(payload=payload)
    )

    assert projected is not None
    assert "draft_claim_cluster_rows" not in projected.payload


def test_projection_does_not_carry_heavy_cluster_bodies() -> None:
    payload = _canonical_payload()
    payload.update(
        {
            "source_claim_refs": ["draft-claim-observation:1"],
            "group_members": [{"claim": "heavy body"}],
            "member_claims": [{"evidence_block": "heavy evidence"}],
            "batches": [{"source_claim_refs": ["draft-claim-observation:1"]}],
        }
    )
    event = _clusters_built_event(payload=payload)

    projected = DraftClaimClusterFrontendWorkflowEventProjector().project(event)

    assert projected is not None
    forbidden_body_keys = {
        "claim",
        "possible_questions",
        "exclusion_scope",
        "evidence_block",
        "source_claim_refs",
        "member_claims",
        "group_members",
    }
    assert not _contains_forbidden_payload_key(
        projected.payload,
        forbidden_body_keys,
    )


def _contains_forbidden_payload_key(
    value: object,
    forbidden_keys: set[str],
) -> bool:
    if isinstance(value, dict):
        return any(
            key in forbidden_keys
            or _contains_forbidden_payload_key(item, forbidden_keys)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(
            _contains_forbidden_payload_key(item, forbidden_keys) for item in value
        )
    return False


@pytest.mark.parametrize(
    "forbidden_key",
    (
        "operation_key",
        "canonical_phase",
        "next_run_after",
        "next_command_type",
        "capacity_retry_at",
    ),
)
def test_projection_excludes_forbidden_payload_fields(forbidden_key: str) -> None:
    projected = DraftClaimClusterFrontendWorkflowEventProjector().project(
        _clusters_built_event()
    )

    assert projected is not None
    assert forbidden_key not in projected.payload


def test_projection_event_id_is_deterministic() -> None:
    event = _clusters_built_event()
    projector = DraftClaimClusterFrontendWorkflowEventProjector()

    first = projector.project(event)
    second = projector.project(event)

    assert first is not None
    assert second is not None
    assert first.projection_event_id == second.projection_event_id
