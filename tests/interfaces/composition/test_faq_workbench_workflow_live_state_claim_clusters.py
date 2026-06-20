from __future__ import annotations

from collections.abc import Mapping

import pytest

from src.interfaces.composition.faq_workbench_workflow_live_state import (
    WorkbenchWorkflowLiveStateQuery,
    _claim_cluster_status,
)


class _FakeConnection:
    def __init__(self, rows: tuple[Mapping[str, object], ...]) -> None:
        self._rows = rows
        self.query = ""
        self.args: tuple[object, ...] = ()

    async def fetch(
        self, query: str, *args: object
    ) -> tuple[Mapping[str, object], ...]:
        self.query = query
        self.args = args
        return self._rows


@pytest.mark.parametrize(
    (
        "counts",
        "expected",
    ),
    (
        ({}, "planned"),
        ({"ready_work_item_count": 1}, "ready"),
        ({"pending_comparison_count": 1}, "comparing"),
        (
            {"active_compacted_node_count": 1, "active_node_count": 2},
            "partially_compacted",
        ),
        ({"active_compacted_node_count": 1, "active_node_count": 1}, "compacted"),
        ({"waiting_comparison_count": 1}, "blocked"),
        ({"terminal_failed_work_item_count": 1}, "failed"),
    ),
)
def test_claim_cluster_status_is_derived_from_persisted_runtime_state(
    counts: dict[str, int],
    expected: str,
) -> None:
    assert _claim_cluster_status(**counts) == expected


@pytest.mark.asyncio
async def test_claim_clusters_query_hydrates_counts_members_and_comparisons() -> None:
    connection = _FakeConnection(
        (
            {
                "group_ref": "group-1",
                "member_count": 2,
                "candidate_edge_count": 1,
                "batch_count": 1,
                "node_count": 3,
                "active_node_count": 2,
                "active_compacted_node_count": 1,
                "comparison_count": 2,
                "pending_comparison_count": 1,
                "waiting_comparison_count": 0,
                "work_item_count": 2,
                "ready_work_item_count": 0,
                "leased_work_item_count": 1,
                "completed_work_item_count": 1,
                "retryable_failed_work_item_count": 0,
                "terminal_failed_work_item_count": 0,
                "user_action_required_work_item_count": 0,
                "members": [
                    {
                        "observation_ref": "claim-1",
                        "claim": "Support is available",
                        "possible_questions": ["When is support available?"],
                        "exclusion_scope": "Holidays are unspecified",
                        "granularity": "atomic",
                        "source_document_ref": "document-1",
                        "source_unit_ref": "section-1",
                        "embedding_ref": "embedding-1",
                        "embedding_model_id": "embedding-model",
                        "embedding_dimensions": 384,
                        "embedding_status": "ready",
                        "node_ref": "node-1",
                        "node_kind": "raw",
                        "node_active": True,
                        "node_status": "active",
                        "member_rank": 0,
                        "member_kind": "draft_claim",
                    },
                    {
                        "observation_ref": "claim-2",
                        "claim": "An operator joins on request",
                        "possible_questions": [],
                        "exclusion_scope": "",
                        "granularity": "atomic",
                        "source_document_ref": "document-1",
                        "source_unit_ref": "section-2",
                        "embedding_ref": "embedding-2",
                        "embedding_model_id": "embedding-model",
                        "embedding_dimensions": 384,
                        "embedding_status": "ready",
                        "node_ref": "node-2",
                        "node_kind": "raw",
                        "node_active": False,
                        "node_status": "superseded",
                        "member_rank": 1,
                        "member_kind": "draft_claim",
                    },
                ],
                "comparisons": [
                    {
                        "comparison_ref": "comparison-1",
                        "cluster_ref": "group-1",
                        "left_node_ref": "node-1",
                        "right_node_ref": "node-2",
                        "status": "pending",
                        "result_node_ref": None,
                        "round_index": 0,
                    }
                ],
            },
        )
    )

    clusters = await WorkbenchWorkflowLiveStateQuery(connection)._claim_clusters(
        workflow_run_id="workflow-1"
    )

    assert connection.args == ("workflow-1",)
    assert connection.query.count("$1") >= 1
    assert "draft_claim_compaction_candidate_edges" in connection.query
    assert "draft_claim_compaction_batches" in connection.query
    assert "draft_claim_compaction_nodes" in connection.query
    assert "draft_claim_compaction_comparisons" in connection.query
    assert "execution_work_items" in connection.query
    assert len(clusters) == 1
    cluster = clusters[0]
    assert cluster.status == "partially_compacted"
    assert cluster.candidate_edge_count == 1
    assert cluster.batch_count == 1
    assert cluster.node_count == 3
    assert cluster.comparison_count == 2
    assert cluster.work_item_count == 2
    assert tuple(member.observation_ref for member in cluster.members) == (
        "claim-1",
        "claim-2",
    )
    assert cluster.members[0].claim == "Support is available"
    assert cluster.members[0].embedding_dimensions == 384
    assert cluster.members[1].node_status == "superseded"
    assert cluster.comparisons[0].comparison_ref == "comparison-1"
