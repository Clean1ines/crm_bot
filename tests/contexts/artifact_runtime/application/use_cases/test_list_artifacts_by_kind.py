from __future__ import annotations

from datetime import datetime, timezone

from src.contexts.artifact_runtime.application.ports.artifact_repository_port import (
    ArtifactRepositoryPort,
)
from src.contexts.artifact_runtime.application.use_cases.list_artifacts_by_kind import (
    ListArtifactsByKind,
    ListArtifactsByKindCommand,
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
    artifact_ref: str,
    artifact_kind: str,
    status: ArtifactStatus = ArtifactStatus.STORED,
) -> PipelineArtifact:
    now = _now()
    return PipelineArtifact(
        artifact_ref=ArtifactRef(artifact_ref),
        artifact_kind=ArtifactKind(artifact_kind),
        payload=ArtifactPayload({"value": 1}),
        status=status,
        visibility=ArtifactVisibility.INTERNAL,
        retention_policy=RetentionPolicy.temporary(),
        lineage=ArtifactLineage(),
        created_at=now,
        updated_at=now,
    )


def test_list_artifacts_by_kind_delegates_to_kind_lookup() -> None:
    artifact_kind = ArtifactKind("generic.step_result")
    matching = _artifact(
        artifact_ref="matching-artifact",
        artifact_kind=artifact_kind.value,
    )
    unrelated = _artifact(
        artifact_ref="unrelated-artifact",
        artifact_kind="generic.other_result",
    )
    repository = FakeArtifactRepository((matching, unrelated))
    use_case = ListArtifactsByKind(repository=repository)

    result = use_case.execute(ListArtifactsByKindCommand(artifact_kind=artifact_kind))

    assert result.artifacts == (matching,)
    assert repository.list_by_kind_calls == [artifact_kind]
    assert repository.list_by_kind_and_status_calls == []


def test_list_artifacts_by_kind_and_status_delegates_to_combined_lookup() -> None:
    artifact_kind = ArtifactKind("generic.step_result")
    matching = _artifact(
        artifact_ref="matching-artifact",
        artifact_kind=artifact_kind.value,
        status=ArtifactStatus.VALIDATED,
    )
    wrong_status = _artifact(
        artifact_ref="wrong-status-artifact",
        artifact_kind=artifact_kind.value,
        status=ArtifactStatus.STORED,
    )
    repository = FakeArtifactRepository((matching, wrong_status))
    use_case = ListArtifactsByKind(repository=repository)

    result = use_case.execute(
        ListArtifactsByKindCommand(
            artifact_kind=artifact_kind,
            status=ArtifactStatus.VALIDATED,
        )
    )

    assert result.artifacts == (matching,)
    assert repository.list_by_kind_calls == []
    assert repository.list_by_kind_and_status_calls == [
        (artifact_kind, ArtifactStatus.VALIDATED)
    ]


def test_list_artifacts_by_kind_does_not_mutate_repository() -> None:
    artifact_kind = ArtifactKind("generic.step_result")
    matching = _artifact(
        artifact_ref="matching-artifact",
        artifact_kind=artifact_kind.value,
    )
    repository = FakeArtifactRepository((matching,))
    use_case = ListArtifactsByKind(repository=repository)

    use_case.execute(ListArtifactsByKindCommand(artifact_kind=artifact_kind))

    assert repository.save_calls == 0
    assert repository.get_calls == []
    assert repository.list_by_parent_ref_calls == []
