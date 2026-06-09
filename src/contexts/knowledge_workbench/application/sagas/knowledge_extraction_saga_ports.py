from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_saga_state import (
    KnowledgeExtractionPhaseCheckpoint,
    KnowledgeExtractionPhaseKey,
    KnowledgeExtractionWorkflowState,
)


@dataclass(frozen=True, slots=True)
class KnowledgeExtractionCommandRecord:
    command_key: str
    workflow_run_id: str
    phase_key: KnowledgeExtractionPhaseKey
    target_context: str
    command_kind: str
    command_payload_hash: str
    status: str
    emitted_at: datetime
    completed_at: datetime | None = None
    result_ref: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.command_key, "command_key")
        _require_non_empty(self.workflow_run_id, "workflow_run_id")
        _require_non_empty(self.target_context, "target_context")
        _require_non_empty(self.command_kind, "command_kind")
        _require_non_empty(self.command_payload_hash, "command_payload_hash")
        _require_non_empty(self.status, "status")
        _require_timezone_aware(self.emitted_at, "emitted_at")
        if self.completed_at is not None:
            _require_timezone_aware(self.completed_at, "completed_at")
            if self.completed_at < self.emitted_at:
                raise ValueError("completed_at must be >= emitted_at")


@dataclass(frozen=True, slots=True)
class KnowledgeExtractionEventCursorRecord:
    consumer_name: str
    event_id: str
    workflow_run_id: str
    event_type: str
    processed_at: datetime
    handler_result: str

    def __post_init__(self) -> None:
        _require_non_empty(self.consumer_name, "consumer_name")
        _require_non_empty(self.event_id, "event_id")
        _require_non_empty(self.workflow_run_id, "workflow_run_id")
        _require_non_empty(self.event_type, "event_type")
        _require_timezone_aware(self.processed_at, "processed_at")
        _require_non_empty(self.handler_result, "handler_result")


class KnowledgeExtractionSagaStateRepositoryPort(Protocol):
    async def load_workflow_state(
        self,
        workflow_run_id: str,
    ) -> KnowledgeExtractionWorkflowState | None: ...

    async def save_workflow_state(
        self,
        state: KnowledgeExtractionWorkflowState,
    ) -> None: ...

    async def save_phase_checkpoint(
        self,
        checkpoint: KnowledgeExtractionPhaseCheckpoint,
    ) -> None: ...


class KnowledgeExtractionCommandLogPort(Protocol):
    async def command_exists(self, command_key: str) -> bool: ...

    async def record_command(
        self,
        command: KnowledgeExtractionCommandRecord,
    ) -> None: ...


class KnowledgeExtractionEventCursorPort(Protocol):
    async def event_was_processed(
        self,
        *,
        consumer_name: str,
        event_id: str,
    ) -> bool: ...

    async def record_processed_event(
        self,
        record: KnowledgeExtractionEventCursorRecord,
    ) -> None: ...


class KnowledgeExtractionCommandEmitterPort(Protocol):
    async def emit_command(
        self,
        *,
        command_key: str,
        target_context: str,
        command_kind: str,
        payload: Mapping[str, object],
    ) -> None: ...


def _require_non_empty(value: str, field_name: str) -> None:
    if not value or not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _require_timezone_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
