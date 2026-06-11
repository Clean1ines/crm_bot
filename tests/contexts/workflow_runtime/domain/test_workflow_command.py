from __future__ import annotations

from datetime import datetime, timezone
from types import MappingProxyType
from typing import cast

import pytest

from src.contexts.workflow_runtime.domain.entities.workflow_command import (
    WorkflowCommand,
    WorkflowCommandStatus,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_command_id import (
    WorkflowCommandId,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_idempotency_key import (
    WorkflowIdempotencyKey,
)


def _now() -> datetime:
    return datetime(2026, 6, 11, 12, 0, tzinfo=timezone.utc)


def _command(
    *,
    command_type: str = "IngestSourceDocument",
    payload: dict[str, object] | None = None,
    run_after: datetime | None = None,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
    attempt_count: int = 0,
) -> WorkflowCommand:
    return WorkflowCommand(
        command_id=WorkflowCommandId("command-1"),
        command_type=command_type,
        workflow_run_id="workflow-1",
        idempotency_key=WorkflowIdempotencyKey("source-ingestion:workflow-1"),
        payload={"source_document_ref": "source-document-1"}
        if payload is None
        else payload,
        status=WorkflowCommandStatus.PENDING,
        run_after=_now() if run_after is None else run_after,
        created_at=_now() if created_at is None else created_at,
        updated_at=_now() if updated_at is None else updated_at,
        attempt_count=attempt_count,
    )


def test_workflow_command_rejects_empty_command_type() -> None:
    with pytest.raises(ValueError, match="command_type must be non-empty"):
        _command(command_type=" ")


def test_workflow_command_freezes_payload() -> None:
    payload = {"count": 1}

    command = _command(payload=payload)
    payload["count"] = 2

    assert isinstance(command.payload, MappingProxyType)
    assert command.payload["count"] == 1
    with pytest.raises(TypeError):
        cast(dict[str, object], command.payload)["count"] = 3


def test_workflow_command_requires_timezone_aware_timestamps() -> None:
    naive = datetime(2026, 6, 11, 12, 0)

    with pytest.raises(ValueError, match="run_after must be timezone-aware"):
        _command(run_after=naive)

    with pytest.raises(ValueError, match="created_at must be timezone-aware"):
        _command(created_at=naive)

    with pytest.raises(ValueError, match="updated_at must be timezone-aware"):
        _command(updated_at=naive)


def test_workflow_command_rejects_negative_attempt_count() -> None:
    with pytest.raises(ValueError, match="attempt_count must be >= 0"):
        _command(attempt_count=-1)
