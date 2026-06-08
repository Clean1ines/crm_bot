from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.contexts.knowledge_workbench.consolidation.domain.clustering.entities.draft_claim_cluster import (
    DraftClaimCluster,
)
from src.contexts.knowledge_workbench.consolidation.domain.clustering.entities.draft_claim_subcluster import (
    DraftClaimSubcluster,
)
from src.contexts.knowledge_workbench.consolidation.domain.clustering.value_objects.cluster_member_ref import (
    ClusterMemberRef,
)
from src.contexts.knowledge_workbench.consolidation.domain.clustering.value_objects.cluster_ref import (
    ClusterRef,
)
from src.contexts.knowledge_workbench.consolidation.domain.clustering.value_objects.subcluster_ref import (
    SubclusterRef,
)
from src.contexts.knowledge_workbench.extraction.domain.value_objects.draft_claim_observation_ref import (
    DraftClaimObservationRef,
)


ROOT = Path(__file__).resolve().parents[6]
CLUSTERING_DOMAIN = (
    ROOT
    / "src"
    / "contexts"
    / "knowledge_workbench"
    / "consolidation"
    / "domain"
    / "clustering"
)


def _now() -> datetime:
    return datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)


def _member(value: str) -> DraftClaimObservationRef:
    return DraftClaimObservationRef(value)


def _cluster(
    *,
    members: tuple[DraftClaimObservationRef, ...] = (
        DraftClaimObservationRef("draft-claim-1"),
        DraftClaimObservationRef("draft-claim-2"),
    ),
    created_at: datetime | None = None,
) -> DraftClaimCluster:
    return DraftClaimCluster(
        cluster_ref=ClusterRef("cluster-1"),
        members=members,
        created_at=created_at or _now(),
    )


def _subcluster(
    *,
    members: tuple[DraftClaimObservationRef, ...] = (
        DraftClaimObservationRef("draft-claim-1"),
        DraftClaimObservationRef("draft-claim-2"),
    ),
    created_at: datetime | None = None,
) -> DraftClaimSubcluster:
    return DraftClaimSubcluster(
        subcluster_ref=SubclusterRef("subcluster-1"),
        parent_cluster_ref=ClusterRef("cluster-1"),
        members=members,
        created_at=created_at or _now(),
    )


def test_draft_claim_cluster_is_valid_with_members() -> None:
    cluster = _cluster()

    assert cluster.cluster_ref.value == "cluster-1"
    assert tuple(member.value for member in cluster.members) == (
        "draft-claim-1",
        "draft-claim-2",
    )
    assert cluster.created_at == _now()


def test_draft_claim_cluster_requires_at_least_one_member() -> None:
    with pytest.raises(ValueError):
        _cluster(members=())


def test_draft_claim_cluster_rejects_duplicate_members() -> None:
    member = _member("draft-claim-1")

    with pytest.raises(ValueError):
        _cluster(members=(member, member))


def test_draft_claim_cluster_requires_timezone_aware_created_at() -> None:
    with pytest.raises(ValueError):
        _cluster(created_at=datetime(2026, 6, 8, 12, 0))


def test_draft_claim_cluster_is_immutable() -> None:
    cluster = _cluster()

    with pytest.raises(FrozenInstanceError):
        setattr(cluster, "members", (_member("changed"),))


def test_draft_claim_subcluster_is_valid_with_parent_cluster_ref() -> None:
    subcluster = _subcluster()

    assert subcluster.subcluster_ref.value == "subcluster-1"
    assert subcluster.parent_cluster_ref.value == "cluster-1"
    assert tuple(member.value for member in subcluster.members) == (
        "draft-claim-1",
        "draft-claim-2",
    )


def test_draft_claim_subcluster_requires_at_least_one_member() -> None:
    with pytest.raises(ValueError):
        _subcluster(members=())


def test_draft_claim_subcluster_rejects_duplicate_members() -> None:
    member = _member("draft-claim-1")

    with pytest.raises(ValueError):
        _subcluster(members=(member, member))


def test_draft_claim_subcluster_requires_timezone_aware_created_at() -> None:
    with pytest.raises(ValueError):
        _subcluster(created_at=datetime(2026, 6, 8, 12, 0))


def test_refs_are_non_empty() -> None:
    with pytest.raises(ValueError):
        ClusterRef(" ")

    with pytest.raises(ValueError):
        SubclusterRef(" ")

    with pytest.raises(ValueError):
        DraftClaimObservationRef(" ")


def test_cluster_member_ref_wraps_draft_claim_observation_ref() -> None:
    member_ref = ClusterMemberRef(DraftClaimObservationRef("draft-claim-1"))

    assert member_ref.value.value == "draft-claim-1"


def test_clustering_subpackage_has_no_later_output_semantics() -> None:
    forbidden_markers = (
        "Surface",
        "surface",
        "Ontology",
        "ontology",
        "CanonicalIntent",
        "ConsolidatedSurface",
        "KnowledgeSurface",
        "Publication",
        "Prompt C output parser",
    )

    offenders: list[str] = []
    for path in CLUSTERING_DOMAIN.rglob("*.py"):
        if path.name == "__init__.py":
            continue
        text = path.read_text(encoding="utf-8")
        for marker in forbidden_markers:
            if marker in text:
                offenders.append(f"{path.relative_to(ROOT)} contains {marker!r}")

    assert not offenders
