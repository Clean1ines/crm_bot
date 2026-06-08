from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.contexts.knowledge_workbench.publication.domain.entities.publication_run import (
    PublicationRun,
)
from src.contexts.knowledge_workbench.publication.domain.value_objects.publication_run_ref import (
    PublicationRunRef,
)
from src.contexts.knowledge_workbench.publication.domain.value_objects.publication_status import (
    PublicationStatus,
)


def _now() -> datetime:
    return datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)


def _run(
    *,
    status: PublicationStatus = PublicationStatus.READY,
    created_at: datetime | None = None,
    completed_at: datetime | None = None,
) -> PublicationRun:
    return PublicationRun(
        publication_run_ref=PublicationRunRef("publication-run-1"),
        status=status,
        created_at=created_at or _now(),
        completed_at=completed_at,
    )


def test_ready_publication_run() -> None:
    run = _run()

    assert run.publication_run_ref.value == "publication-run-1"
    assert run.status is PublicationStatus.READY
    assert run.created_at == _now()
    assert run.completed_at is None


def test_publication_status_values() -> None:
    assert tuple(status.value for status in PublicationStatus) == (
        "ready",
        "running",
        "completed",
        "failed",
        "cancelled",
    )


def test_publication_status_terminal_flags() -> None:
    assert PublicationStatus.COMPLETED.is_terminal
    assert PublicationStatus.FAILED.is_terminal
    assert PublicationStatus.CANCELLED.is_terminal
    assert not PublicationStatus.READY.is_terminal
    assert not PublicationStatus.RUNNING.is_terminal


def test_publication_run_ref_must_be_non_empty() -> None:
    with pytest.raises(ValueError):
        PublicationRunRef(" ")


def test_created_at_must_be_timezone_aware() -> None:
    with pytest.raises(ValueError):
        _run(created_at=datetime(2026, 6, 8, 12, 0))


def test_completed_at_must_be_timezone_aware() -> None:
    with pytest.raises(ValueError):
        _run(
            status=PublicationStatus.COMPLETED,
            completed_at=datetime(2026, 6, 8, 12, 0),
        )


def test_terminal_publication_run_requires_completed_at() -> None:
    with pytest.raises(ValueError):
        _run(status=PublicationStatus.COMPLETED)


def test_non_terminal_publication_run_rejects_completed_at() -> None:
    with pytest.raises(ValueError):
        _run(
            status=PublicationStatus.RUNNING,
            completed_at=_now() + timedelta(seconds=1),
        )


def test_completed_at_must_be_after_created_at() -> None:
    with pytest.raises(ValueError):
        _run(
            status=PublicationStatus.COMPLETED,
            completed_at=_now() - timedelta(seconds=1),
        )


def test_completed_publication_run() -> None:
    completed_at = _now() + timedelta(seconds=1)

    run = _run(
        status=PublicationStatus.COMPLETED,
        completed_at=completed_at,
    )

    assert run.status is PublicationStatus.COMPLETED
    assert run.completed_at == completed_at
