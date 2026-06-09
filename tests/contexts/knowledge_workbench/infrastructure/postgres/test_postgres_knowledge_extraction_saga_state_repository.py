from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from src.contexts.knowledge_workbench.application.sagas import (
    KnowledgeExtractionCommandRecord,
    KnowledgeExtractionEventCursorRecord,
    KnowledgeExtractionPhaseCheckpoint,
    KnowledgeExtractionPhaseKey,
    KnowledgeExtractionPhaseStatus,
    KnowledgeExtractionWorkflowState,
    KnowledgeExtractionWorkflowStatus,
)
from src.contexts.knowledge_workbench.infrastructure.postgres.postgres_knowledge_extraction_saga_state_repository import (
    PostgresKnowledgeExtractionSagaStateRepository,
)

ROOT = Path(__file__).resolve().parents[5]
ADAPTER = ROOT / "src/contexts/knowledge_workbench/infrastructure/postgres/postgres_knowledge_extraction_saga_state_repository.py"


def now() -> datetime:
    return datetime(2026, 6, 9, 12, 0, tzinfo=timezone.utc)


class FakeConnection:
    def __init__(self) -> None:
        self.workflows: dict[str, dict[str, object]] = {}
        self.checkpoints: dict[tuple[str, str], dict[str, object]] = {}
        self.commands: dict[str, dict[str, object]] = {}
        self.events: dict[tuple[str, str], dict[str, object]] = {}

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        return self.workflows.get(str(args[0]))

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        workflow_run_id = str(args[0])
        rows = [
            row
            for (row_workflow_run_id, _phase_key), row in self.checkpoints.items()
            if row_workflow_run_id == workflow_run_id
        ]
        return sorted(rows, key=lambda row: (row["updated_at"], row["phase_key"]))

    async def execute(self, query: str, *args: object) -> object:
        if "knowledge_extraction_workflow_runs" in query:
            self.workflows[str(args[0])] = {
                "workflow_run_id": args[0],
                "project_id": args[1],
                "source_document_ref": args[2],
                "status": args[3],
                "current_phase": args[4],
                "pause_reason": args[5],
                "failure_kind": args[6],
                "failure_message": args[7],
                "review_status": args[8],
                "publication_ref": args[9],
                "cleanup_status": args[10],
                "created_at": args[11],
                "updated_at": args[12],
                "completed_at": args[13],
                "cancelled_at": args[14],
            }
            return "OK"
        if "knowledge_extraction_phase_checkpoints" in query:
            self.checkpoints[(str(args[0]), str(args[1]))] = {
                "workflow_run_id": args[0],
                "phase_key": args[1],
                "phase_status": args[2],
                "expected_count": args[3],
                "completed_count": args[4],
                "failed_count": args[5],
                "blocked_count": args[6],
                "idempotency_key": args[7],
                "last_event_ref": args[8],
                "checkpoint_payload": args[9],
                "updated_at": args[10],
            }
            return "OK"
        if "knowledge_extraction_command_log" in query:
            self.commands.setdefault(
                str(args[0]),
                {
                    "command_key": args[0],
                    "workflow_run_id": args[1],
                    "phase_key": args[2],
                    "target_context": args[3],
                    "command_kind": args[4],
                    "command_payload_hash": args[5],
                    "status": args[6],
                    "emitted_at": args[7],
                    "completed_at": args[8],
                    "result_ref": args[9],
                },
            )
            return "OK"
        if "knowledge_extraction_event_cursor" in query:
            self.events.setdefault(
                (str(args[0]), str(args[1])),
                {
                    "consumer_name": args[0],
                    "event_id": args[1],
                    "workflow_run_id": args[2],
                    "event_type": args[3],
                    "processed_at": args[4],
                    "handler_result": args[5],
                },
            )
            return "OK"
        raise AssertionError(query)

    async def fetchval(self, query: str, *args: object) -> object:
        if "knowledge_extraction_command_log" in query:
            return str(args[0]) in self.commands
        if "knowledge_extraction_event_cursor" in query:
            return (str(args[0]), str(args[1])) in self.events
        raise AssertionError(query)


def test_saves_and_loads_workflow_state_with_checkpoints() -> None:
    import asyncio

    connection = FakeConnection()
    repository = PostgresKnowledgeExtractionSagaStateRepository(connection)
    checkpoint = KnowledgeExtractionPhaseCheckpoint(
        workflow_run_id="workflow-1",
        phase_key=KnowledgeExtractionPhaseKey.SOURCE_UNITS_CREATED,
        phase_status=KnowledgeExtractionPhaseStatus.COMPLETED,
        expected_count=2,
        completed_count=2,
        checkpoint_payload={"source_unit_refs": ["unit-1", "unit-2"]},
        updated_at=now(),
    )
    state = KnowledgeExtractionWorkflowState(
        workflow_run_id="workflow-1",
        project_id="project-1",
        source_document_ref="source-document-1",
        status=KnowledgeExtractionWorkflowStatus.RUNNING,
        current_phase=KnowledgeExtractionPhaseKey.SOURCE_UNITS_CREATED,
        checkpoints=(checkpoint,),
        created_at=now(),
        updated_at=now(),
    )

    async def run() -> KnowledgeExtractionWorkflowState | None:
        await repository.save_workflow_state(state)
        await repository.save_phase_checkpoint(checkpoint)
        return await repository.load_workflow_state("workflow-1")

    loaded = asyncio.run(run())

    assert loaded is not None
    assert loaded.workflow_run_id == "workflow-1"
    assert loaded.project_id == "project-1"
    assert loaded.source_document_ref == "source-document-1"
    assert loaded.status is KnowledgeExtractionWorkflowStatus.RUNNING
    assert loaded.current_phase is KnowledgeExtractionPhaseKey.SOURCE_UNITS_CREATED
    assert loaded.checkpoints[0].checkpoint_payload["source_unit_refs"] == [
        "unit-1",
        "unit-2",
    ]


def test_returns_none_for_missing_workflow_state() -> None:
    import asyncio

    repository = PostgresKnowledgeExtractionSagaStateRepository(FakeConnection())

    assert asyncio.run(repository.load_workflow_state("missing")) is None


def test_command_log_is_idempotent() -> None:
    import asyncio

    connection = FakeConnection()
    repository = PostgresKnowledgeExtractionSagaStateRepository(connection)
    command = KnowledgeExtractionCommandRecord(
        command_key="command-1",
        workflow_run_id="workflow-1",
        phase_key=KnowledgeExtractionPhaseKey.SOURCE_UNITS_CREATED,
        target_context="knowledge_workbench/source_management",
        command_kind="CreateSourceUnits",
        command_payload_hash="hash-1",
        status="emitted",
        emitted_at=now(),
    )

    async def run() -> bool:
        await repository.record_command(command)
        exists = await repository.command_exists("command-1")
        await repository.record_command(command)
        return exists

    assert asyncio.run(run()) is True
    assert len(connection.commands) == 1


def test_event_cursor_is_idempotent() -> None:
    import asyncio

    connection = FakeConnection()
    repository = PostgresKnowledgeExtractionSagaStateRepository(connection)
    event = KnowledgeExtractionEventCursorRecord(
        consumer_name="knowledge-extraction-saga",
        event_id="event-1",
        workflow_run_id="workflow-1",
        event_type="SourceUnitCreated",
        processed_at=now(),
        handler_result="advanced",
    )

    async def run() -> bool:
        await repository.record_processed_event(event)
        exists = await repository.event_was_processed(
            consumer_name="knowledge-extraction-saga",
            event_id="event-1",
        )
        await repository.record_processed_event(event)
        return exists

    assert asyncio.run(run()) is True
    assert len(connection.events) == 1


def test_source_guard() -> None:
    text = ADAPTER.read_text(encoding="utf-8")

    required = (
        "PostgresKnowledgeExtractionSagaStateRepository",
        "AsyncKnowledgeExtractionSagaConnectionLike",
        "KnowledgeExtractionSagaStateRepositoryPort",
        "KnowledgeExtractionCommandLogPort",
        "KnowledgeExtractionEventCursorPort",
        "knowledge_extraction_workflow_runs",
        "knowledge_extraction_phase_checkpoints",
        "knowledge_extraction_command_log",
        "knowledge_extraction_event_cursor",
        "ON CONFLICT",
    )
    forbidden = (
        "asyncpg",
        "src.infrastructure",
        "JobDispatcher",
        "worker_loop",
        "outbox_events",
        "published_at",
        "Groq",
        "Qwen",
        "knowledge_workbench_processing_runs",
        "SectionBatchQueueItem",
        "workbench_parallel_processing",
        "process_workbench_document",
        "RunClaimExtractionStageAsync",
        "RecordClaimExtractionSuccess",
        "ProcessClaimExtractionWorkItem",
        "ApplyDraftClaimObservationArtifactAsync",
    )

    missing = [marker for marker in required if marker not in text]
    offenders = [marker for marker in forbidden if marker in text]

    assert not missing, "\n".join(missing)
    assert not offenders, "\n".join(offenders)
