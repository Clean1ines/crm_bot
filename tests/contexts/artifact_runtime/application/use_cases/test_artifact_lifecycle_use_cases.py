from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import pytest

from src.contexts.artifact_runtime.application.ports.artifact_unit_of_work_port import (
    ArtifactEvent,
)
from src.contexts.artifact_runtime.application.use_cases.expire_artifact import (
    ExpireArtifact,
    ExpireArtifactCommand,
)
from src.contexts.artifact_runtime.application.use_cases.reject_artifact import (
    RejectArtifact,
    RejectArtifactCommand,
)
from src.contexts.artifact_runtime.application.use_cases.supersede_artifact import (
    SupersedeArtifact,
    SupersedeArtifactCommand,
)
from src.contexts.artifact_runtime.application.use_cases.validate_artifact import (
    ValidateArtifact,
    ValidateArtifactCommand,
)
from src.contexts.artifact_runtime.domain.entities.pipeline_artifact import (
    PipelineArtifact,
)
from src.contexts.artifact_runtime.domain.events.artifact_events import (
    ArtifactExpired,
    ArtifactRejected,
    ArtifactSuperseded,
    ArtifactValidated,
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


@dataclass(slots=True)
class FakeArtifactUnitOfWork:
    saved_artifacts: list[PipelineArtifact] = field(default_factory=list)
    appended_events: list[ArtifactEvent] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
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


def _artifact(status: ArtifactStatus = ArtifactStatus.STORED) -> PipelineArtifact:
    now = _now()
    return PipelineArtifact(
        artifact_ref=ArtifactRef("artifact-1"),
        artifact_kind=ArtifactKind("llm_runtime.raw_output"),
        payload=ArtifactPayload({"raw_text": '{"ok": true}'}),
        status=status,
        visibility=ArtifactVisibility.INTERNAL,
        retention_policy=RetentionPolicy.temporary(),
        lineage=ArtifactLineage(),
        created_at=now,
        updated_at=now,
    )


def _assert_committed(unit_of_work: FakeArtifactUnitOfWork) -> None:
    assert unit_of_work.committed
    assert not unit_of_work.rolled_back
    assert unit_of_work.actions == [
        "save_artifact",
        "append_event",
        "commit",
    ]


def test_validate_artifact_commits_validated_artifact_and_event() -> None:
    unit_of_work = FakeArtifactUnitOfWork()
    occurred_at = _now() + timedelta(seconds=1)

    result = ValidateArtifact(repository=unit_of_work).execute(
        ValidateArtifactCommand(
            artifact=_artifact(),
            occurred_at=occurred_at,
        ),
    )

    assert result.artifact.status is ArtifactStatus.VALIDATED
    assert result.artifact.updated_at == occurred_at
    assert isinstance(result.event, ArtifactValidated)
    assert unit_of_work.saved_artifacts == [result.artifact]
    assert unit_of_work.appended_events == [result.event]
    _assert_committed(unit_of_work)


def test_reject_artifact_commits_rejected_artifact_and_event() -> None:
    unit_of_work = FakeArtifactUnitOfWork()
    occurred_at = _now() + timedelta(seconds=1)

    result = RejectArtifact(repository=unit_of_work).execute(
        RejectArtifactCommand(
            artifact=_artifact(),
            occurred_at=occurred_at,
        ),
    )

    assert result.artifact.status is ArtifactStatus.REJECTED
    assert result.artifact.status.is_terminal
    assert result.artifact.updated_at == occurred_at
    assert isinstance(result.event, ArtifactRejected)
    _assert_committed(unit_of_work)


def test_supersede_artifact_commits_superseded_artifact_and_event() -> None:
    unit_of_work = FakeArtifactUnitOfWork()
    occurred_at = _now() + timedelta(seconds=1)

    result = SupersedeArtifact(repository=unit_of_work).execute(
        SupersedeArtifactCommand(
            artifact=_artifact(),
            occurred_at=occurred_at,
        ),
    )

    assert result.artifact.status is ArtifactStatus.SUPERSEDED
    assert result.artifact.status.is_terminal
    assert result.artifact.updated_at == occurred_at
    assert isinstance(result.event, ArtifactSuperseded)
    _assert_committed(unit_of_work)


def test_expire_artifact_commits_expired_artifact_and_event() -> None:
    unit_of_work = FakeArtifactUnitOfWork()
    occurred_at = _now() + timedelta(seconds=1)

    result = ExpireArtifact(repository=unit_of_work).execute(
        ExpireArtifactCommand(
            artifact=_artifact(),
            occurred_at=occurred_at,
        ),
    )

    assert result.artifact.status is ArtifactStatus.EXPIRED
    assert result.artifact.status.is_terminal
    assert result.artifact.updated_at == occurred_at
    assert isinstance(result.event, ArtifactExpired)
    _assert_committed(unit_of_work)


def test_lifecycle_use_case_rolls_back_when_commit_fails() -> None:
    unit_of_work = FakeArtifactUnitOfWork(fail_on_commit=True)

    with pytest.raises(RuntimeError, match="commit failed"):
        ValidateArtifact(repository=unit_of_work).execute(
            ValidateArtifactCommand(
                artifact=_artifact(),
                occurred_at=_now() + timedelta(seconds=1),
            ),
        )

    assert not unit_of_work.committed
    assert unit_of_work.rolled_back
    assert unit_of_work.actions == [
        "save_artifact",
        "append_event",
        "commit",
        "rollback",
    ]


def test_lifecycle_commands_require_timezone_aware_occurred_at() -> None:
    naive = datetime(2026, 6, 8, 12, 0)

    with pytest.raises(ValueError):
        ValidateArtifactCommand(artifact=_artifact(), occurred_at=naive)

    with pytest.raises(ValueError):
        RejectArtifactCommand(artifact=_artifact(), occurred_at=naive)

    with pytest.raises(ValueError):
        SupersedeArtifactCommand(artifact=_artifact(), occurred_at=naive)

    with pytest.raises(ValueError):
        ExpireArtifactCommand(artifact=_artifact(), occurred_at=naive)


def test_terminal_artifact_cannot_transition_again_through_use_case() -> None:
    unit_of_work = FakeArtifactUnitOfWork()
    terminal = _artifact().reject(updated_at=_now() + timedelta(seconds=1))

    with pytest.raises(ValueError):
        ValidateArtifact(repository=unit_of_work).execute(
            ValidateArtifactCommand(
                artifact=terminal,
                occurred_at=_now() + timedelta(seconds=2),
            ),
        )

    assert unit_of_work.actions == []
