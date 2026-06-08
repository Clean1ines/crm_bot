from __future__ import annotations

from datetime import datetime, timezone

from src.contexts.artifact_runtime.application.ports.artifact_repository_port import (
    ArtifactRepositoryPort,
)
from src.contexts.artifact_runtime.domain.entities.pipeline_artifact import (
    PipelineArtifact,
)
from src.contexts.artifact_runtime.domain.value_objects.artifact_kind import (
    ArtifactKind,
)
from src.contexts.artifact_runtime.domain.value_objects.artifact_lineage import (
    ArtifactLineage,
)
from src.contexts.artifact_runtime.domain.value_objects.artifact_payload import (
    ArtifactPayload,
)
from src.contexts.artifact_runtime.domain.value_objects.artifact_ref import ArtifactRef
from src.contexts.artifact_runtime.domain.value_objects.artifact_status import (
    ArtifactStatus,
)
from src.contexts.artifact_runtime.domain.value_objects.artifact_visibility import (
    ArtifactVisibility,
)
from src.contexts.artifact_runtime.domain.value_objects.retention_policy import (
    RetentionPolicy,
)


class FakeArtifactRepository(ArtifactRepositoryPort):
    def __init__(self) -> None:
        self._artifacts: dict[ArtifactRef, PipelineArtifact] = {}

    def save(self, artifact: PipelineArtifact) -> None:
        self._artifacts[artifact.artifact_ref] = artifact

    def get(self, artifact_ref: ArtifactRef) -> PipelineArtifact | None:
        return self._artifacts.get(artifact_ref)

    def list_by_parent_ref(
        self,
        parent_ref: ArtifactRef,
    ) -> tuple[PipelineArtifact, ...]:
        return tuple(
            artifact
            for artifact in self._artifacts.values()
            if parent_ref in artifact.lineage.parent_refs
        )

    def list_by_kind(
        self,
        artifact_kind: ArtifactKind,
    ) -> tuple[PipelineArtifact, ...]:
        return tuple(
            artifact
            for artifact in self._artifacts.values()
            if artifact.artifact_kind == artifact_kind
        )

    def list_by_kind_and_status(
        self,
        *,
        artifact_kind: ArtifactKind,
        status: ArtifactStatus,
    ) -> tuple[PipelineArtifact, ...]:
        return tuple(
            artifact
            for artifact in self._artifacts.values()
            if artifact.artifact_kind == artifact_kind and artifact.status is status
        )


def _now() -> datetime:
    return datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)


def _artifact(
    *,
    artifact_ref: str = "artifact-1",
    artifact_kind: str = "generic.step_result",
    status: ArtifactStatus = ArtifactStatus.STORED,
    parent_refs: tuple[ArtifactRef, ...] = (),
    payload: ArtifactPayload | None = None,
) -> PipelineArtifact:
    now = _now()
    return PipelineArtifact(
        artifact_ref=ArtifactRef(artifact_ref),
        artifact_kind=ArtifactKind(artifact_kind),
        payload=payload or ArtifactPayload({"value": 1}),
        status=status,
        visibility=ArtifactVisibility.INTERNAL,
        retention_policy=RetentionPolicy.temporary(),
        lineage=ArtifactLineage(parent_refs),
        created_at=now,
        updated_at=now,
    )


def test_save_and_get_returns_same_artifact() -> None:
    repository = FakeArtifactRepository()
    artifact = _artifact()

    repository.save(artifact)

    assert repository.get(artifact.artifact_ref) is artifact


def test_get_missing_ref_returns_none() -> None:
    repository = FakeArtifactRepository()

    assert repository.get(ArtifactRef("missing-artifact")) is None


def test_list_by_parent_ref_uses_artifact_lineage_parent_refs() -> None:
    repository = FakeArtifactRepository()
    parent_ref = ArtifactRef("parent-artifact")
    matching = _artifact(
        artifact_ref="artifact-matching-parent",
        parent_refs=(parent_ref,),
    )
    unrelated = _artifact(artifact_ref="artifact-unrelated")

    repository.save(matching)
    repository.save(unrelated)

    assert repository.list_by_parent_ref(parent_ref) == (matching,)


def test_list_by_kind_filters_by_artifact_kind() -> None:
    repository = FakeArtifactRepository()
    matching = _artifact(
        artifact_ref="artifact-matching-kind",
        artifact_kind="knowledge_workbench.claim_observations.parsed",
    )
    unrelated = _artifact(
        artifact_ref="artifact-unrelated-kind",
        artifact_kind="knowledge_workbench.claim_observations.raw",
    )

    repository.save(matching)
    repository.save(unrelated)

    assert repository.list_by_kind(
        ArtifactKind("knowledge_workbench.claim_observations.parsed")
    ) == (matching,)


def test_list_by_kind_and_status_filters_by_kind_and_status() -> None:
    repository = FakeArtifactRepository()
    matching = _artifact(
        artifact_ref="artifact-matching-kind-status",
        artifact_kind="generic.step_result",
        status=ArtifactStatus.VALIDATED,
    )
    wrong_status = _artifact(
        artifact_ref="artifact-wrong-status",
        artifact_kind="generic.step_result",
        status=ArtifactStatus.STORED,
    )
    wrong_kind = _artifact(
        artifact_ref="artifact-wrong-kind",
        artifact_kind="generic.other_result",
        status=ArtifactStatus.VALIDATED,
    )

    repository.save(matching)
    repository.save(wrong_status)
    repository.save(wrong_kind)

    assert repository.list_by_kind_and_status(
        artifact_kind=ArtifactKind("generic.step_result"),
        status=ArtifactStatus.VALIDATED,
    ) == (matching,)


def test_artifact_payload_remains_opaque_to_repository() -> None:
    repository = FakeArtifactRepository()
    artifact = _artifact(
        artifact_ref="artifact-opaque-payload",
        payload=ArtifactPayload({"business_payload": "stored_without_interpretation"}),
    )

    repository.save(artifact)

    assert repository.get(artifact.artifact_ref) is artifact
