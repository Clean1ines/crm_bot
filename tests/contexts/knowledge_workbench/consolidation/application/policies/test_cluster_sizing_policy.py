from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.contexts.knowledge_workbench.consolidation.application.policies.cluster_sizing_policy import (
    ClusterSizingInput,
    ClusterSizingPolicy,
)
from src.contexts.knowledge_workbench.consolidation.domain.clustering.entities.draft_claim_cluster import (
    DraftClaimCluster,
)
from src.contexts.knowledge_workbench.consolidation.domain.clustering.value_objects.cluster_ref import (
    ClusterRef,
)
from src.contexts.knowledge_workbench.extraction.domain.value_objects.draft_claim_observation_ref import (
    DraftClaimObservationRef,
)


ROOT = Path(__file__).resolve().parents[6]
POLICY_FILE = (
    ROOT
    / "src"
    / "contexts"
    / "knowledge_workbench"
    / "consolidation"
    / "application"
    / "policies"
    / "cluster_sizing_policy.py"
)


def _now() -> datetime:
    return datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)


def _member(index: int) -> DraftClaimObservationRef:
    return DraftClaimObservationRef(f"draft-claim-{index}")


def _cluster(
    *,
    member_count: int,
    cluster_ref: str = "cluster-1",
) -> DraftClaimCluster:
    return DraftClaimCluster(
        cluster_ref=ClusterRef(cluster_ref),
        members=tuple(_member(index) for index in range(member_count)),
        created_at=_now(),
    )


def _split(
    cluster: DraftClaimCluster,
    *,
    max_members_per_request: int,
):
    return ClusterSizingPolicy().split(
        ClusterSizingInput(
            cluster=cluster,
            max_members_per_request=max_members_per_request,
        )
    )


def test_cluster_with_members_within_limit_returns_one_subcluster() -> None:
    cluster = _cluster(member_count=3)

    result = _split(cluster, max_members_per_request=3)

    assert len(result.subclusters) == 1
    assert result.subclusters[0].parent_cluster_ref == cluster.cluster_ref
    assert result.subclusters[0].members == cluster.members
    assert result.subclusters[0].created_at == cluster.created_at


def test_cluster_larger_than_limit_is_split_into_chunks() -> None:
    cluster = _cluster(member_count=5)

    result = _split(cluster, max_members_per_request=2)

    assert tuple(len(subcluster.members) for subcluster in result.subclusters) == (
        2,
        2,
        1,
    )


def test_split_preserves_member_order() -> None:
    cluster = _cluster(member_count=5)

    result = _split(cluster, max_members_per_request=2)

    flattened_members = tuple(
        member for subcluster in result.subclusters for member in subcluster.members
    )

    assert flattened_members == cluster.members


def test_subcluster_refs_are_deterministic() -> None:
    cluster = _cluster(member_count=5, cluster_ref="cluster-abc")

    result = _split(cluster, max_members_per_request=2)

    assert tuple(
        subcluster.subcluster_ref.value for subcluster in result.subclusters
    ) == (
        "cluster-abc.subcluster.0",
        "cluster-abc.subcluster.1",
        "cluster-abc.subcluster.2",
    )


def test_exact_limit_returns_one_subcluster() -> None:
    cluster = _cluster(member_count=4)

    result = _split(cluster, max_members_per_request=4)

    assert len(result.subclusters) == 1
    assert result.subclusters[0].members == cluster.members


def test_max_members_per_request_must_be_positive() -> None:
    cluster = _cluster(member_count=1)

    with pytest.raises(ValueError):
        ClusterSizingInput(cluster=cluster, max_members_per_request=0)

    with pytest.raises(ValueError):
        ClusterSizingInput(cluster=cluster, max_members_per_request=-1)


def test_cluster_sizing_policy_has_no_runtime_db_or_output_semantics() -> None:
    text = POLICY_FILE.read_text(encoding="utf-8")

    forbidden_markers = (
        "LLM",
        "llm",
        "Postgres",
        "postgres",
        ".commit(",
        ".rollback(",
        "Ontology",
        "ontology",
        "ConsolidatedSurface",
        "KnowledgeSurface",
        "SurfaceKind",
        "final",
    )

    offenders = [marker for marker in forbidden_markers if marker in text]

    assert not offenders
