from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from src.contexts.artifact_runtime.application.ports.artifact_unit_of_work_port import (
    ArtifactEvent,
)
from src.contexts.artifact_runtime.application.use_cases.persist_artifact import (
    PersistArtifact,
    PersistArtifactCommand,
)
from src.contexts.artifact_runtime.domain.entities.pipeline_artifact import (
    PipelineArtifact,
)
from src.contexts.artifact_runtime.domain.events.artifact_events import ArtifactStored
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
    RetentionPolicyKind,
)


@dataclass(slots=True)
class FakeArtifactUnitOfWork:
    saved_artifacts: list[PipelineArtifact] = field(default_factory=list)
    appended_events: list[ArtifactEvent] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    committed: bool = False
    rolled_back: bool = False
    fail_on_commit: bool = False

    def save_artifact(self, artifact: PipelineArtifact) -> None:
        self.actions.append("save_artifact")
        self.saved_artifacts.append(artifact)

    def append_event(self, event: ArtifactEvent) -> None:
        self.actions.append("append_event")
        self.appended_events.append(event)

    def commit(self) -> None:
        self.actions.append("commit")
        if self.fail_on_commit:
            raise RuntimeError("commit failed")
        self.committed = True

    def rollback(self) -> None:
        self.actions.append("rollback")
        self.rolled_back = True


def _now() -> datetime:
    return datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)


def _command() -> PersistArtifactCommand:
    return PersistArtifactCommand(
        artifact_ref=ArtifactRef("artifact-1"),
        artifact_kind=ArtifactKind("llm_runtime.raw_output"),
        payload=ArtifactPayload(
            {
                "task_id": "task-1",
                "raw_text": '{"ok": true}',
            },
        ),
        visibility=ArtifactVisibility.INTERNAL,
        retention_policy=RetentionPolicy.temporary(),
        lineage=ArtifactLineage(),
        occurred_at=_now(),
    )


def test_persist_artifact_commits_stored_artifact_and_event() -> None:
    unit_of_work = FakeArtifactUnitOfWork()

    result = PersistArtifact(unit_of_work=unit_of_work).execute(_command())

    assert result.artifact.artifact_ref == ArtifactRef("artifact-1")
    assert result.artifact.artifact_kind == ArtifactKind("llm_runtime.raw_output")
    assert result.artifact.status is ArtifactStatus.STORED
    assert result.artifact.visibility is ArtifactVisibility.INTERNAL
    assert result.artifact.retention_policy.kind is RetentionPolicyKind.TEMPORARY
    assert result.artifact.created_at == _now()
    assert result.artifact.updated_at == _now()
    assert result.artifact.payload.value["task_id"] == "task-1"

    assert isinstance(result.event, ArtifactStored)
    assert result.event.artifact_ref == ArtifactRef("artifact-1")
    assert result.event.occurred_at == _now()

    assert unit_of_work.saved_artifacts == [result.artifact]
    assert unit_of_work.appended_events == [result.event]
    assert unit_of_work.committed
    assert not unit_of_work.rolled_back
    assert unit_of_work.actions == [
        "save_artifact",
        "append_event",
        "commit",
    ]


def test_persist_artifact_preserves_lineage() -> None:
    unit_of_work = FakeArtifactUnitOfWork()
    parent_ref = ArtifactRef("parent-artifact-1")
    command = PersistArtifactCommand(
        artifact_ref=ArtifactRef("artifact-2"),
        artifact_kind=ArtifactKind("llm_runtime.parsed_output"),
        payload=ArtifactPayload({"parsed": True}),
        visibility=ArtifactVisibility.REVIEWABLE,
        retention_policy=RetentionPolicy.until_superseded(),
        lineage=ArtifactLineage(parent_refs=(parent_ref,)),
        occurred_at=_now(),
    )

    result = PersistArtifact(unit_of_work=unit_of_work).execute(command)

    assert result.artifact.lineage.parent_refs == (parent_ref,)
    assert result.artifact.visibility is ArtifactVisibility.REVIEWABLE
    assert result.artifact.retention_policy.kind is RetentionPolicyKind.UNTIL_SUPERSEDED


def test_persist_artifact_rolls_back_when_commit_fails() -> None:
    unit_of_work = FakeArtifactUnitOfWork(fail_on_commit=True)

    with pytest.raises(RuntimeError, match="commit failed"):
        PersistArtifact(unit_of_work=unit_of_work).execute(_command())

    assert not unit_of_work.committed
    assert unit_of_work.rolled_back
    assert unit_of_work.actions == [
        "save_artifact",
        "append_event",
        "commit",
        "rollback",
    ]


def test_persist_artifact_command_requires_timezone_aware_occurred_at() -> None:
    with pytest.raises(ValueError):
        PersistArtifactCommand(
            artifact_ref=ArtifactRef("artifact-1"),
            artifact_kind=ArtifactKind("llm_runtime.raw_output"),
            payload=ArtifactPayload({}),
            visibility=ArtifactVisibility.INTERNAL,
            retention_policy=RetentionPolicy.temporary(),
            lineage=ArtifactLineage(),
            occurred_at=datetime(2026, 6, 8, 12, 0),
        )
