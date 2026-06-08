from __future__ import annotations

from datetime import datetime, timezone

from src.contexts.artifact_runtime.application.ports.artifact_repository_port import (
    ArtifactRepositoryPort,
)
from src.contexts.artifact_runtime.application.use_cases.load_artifact import (
    LoadArtifact,
    LoadArtifactCommand,
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
    def __init__(self, artifacts: tuple[PipelineArtifact, ...] = ()) -> None:
        self._artifacts = {artifact.artifact_ref: artifact for artifact in artifacts}
        self.save_calls = 0
        self.get_calls: list[ArtifactRef] = []
        self.list_by_parent_ref_calls: list[ArtifactRef] = []
        self.list_by_kind_calls: list[ArtifactKind] = []
        self.list_by_kind_and_status_calls: list[
            tuple[ArtifactKind, ArtifactStatus]
        ] = []

    def save(self, artifact: PipelineArtifact) -> None:
        self.save_calls += 1
        self._artifacts[artifact.artifact_ref] = artifact

    def get(self, artifact_ref: ArtifactRef) -> PipelineArtifact | None:
        self.get_calls.append(artifact_ref)
        return self._artifacts.get(artifact_ref)

    def list_by_parent_ref(
        self,
        parent_ref: ArtifactRef,
    ) -> tuple[PipelineArtifact, ...]:
        self.list_by_parent_ref_calls.append(parent_ref)
        return tuple(
            artifact
            for artifact in self._artifacts.values()
            if parent_ref in artifact.lineage.parent_refs
        )

    def list_by_kind(
        self,
        artifact_kind: ArtifactKind,
    ) -> tuple[PipelineArtifact, ...]:
        self.list_by_kind_calls.append(artifact_kind)
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
        self.list_by_kind_and_status_calls.append((artifact_kind, status))
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
) -> PipelineArtifact:
    now = _now()
    return PipelineArtifact(
        artifact_ref=ArtifactRef(artifact_ref),
        artifact_kind=ArtifactKind(artifact_kind),
        payload=ArtifactPayload({"value": 1}),
        status=status,
        visibility=ArtifactVisibility.INTERNAL,
        retention_policy=RetentionPolicy.temporary(),
        lineage=ArtifactLineage(parent_refs),
        created_at=now,
        updated_at=now,
    )


def test_load_existing_artifact_delegates_to_repository_get() -> None:
    artifact = _artifact()
    repository = FakeArtifactRepository((artifact,))
    use_case = LoadArtifact(repository=repository)

    result = use_case.execute(LoadArtifactCommand(artifact_ref=artifact.artifact_ref))

    assert result.artifact is artifact
    assert repository.get_calls == [artifact.artifact_ref]


def test_load_missing_artifact_returns_none() -> None:
    repository = FakeArtifactRepository()
    use_case = LoadArtifact(repository=repository)
    missing_ref = ArtifactRef("missing-artifact")

    result = use_case.execute(LoadArtifactCommand(artifact_ref=missing_ref))

    assert result.artifact is None
    assert repository.get_calls == [missing_ref]


def test_load_artifact_does_not_mutate_repository() -> None:
    artifact = _artifact()
    repository = FakeArtifactRepository((artifact,))
    use_case = LoadArtifact(repository=repository)

    use_case.execute(LoadArtifactCommand(artifact_ref=artifact.artifact_ref))

    assert repository.save_calls == 0
    assert repository.list_by_parent_ref_calls == []
    assert repository.list_by_kind_calls == []
    assert repository.list_by_kind_and_status_calls == []
