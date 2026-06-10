from datetime import datetime, timezone
from pathlib import Path
from typing import cast

import pytest

from src.contexts.knowledge_workbench.application.sagas.create_source_units_for_ingestion import (
    CreateSourceUnitsForIngestionCommand,
    CreateSourceUnitsForIngestionResult,
)
from src.contexts.knowledge_workbench.application.sagas.persist_accepted_source_ingestion_plan import (
    PersistAcceptedSourceIngestionPlanCommand,
    PersistAcceptedSourceIngestionPlanResult,
)
from src.contexts.knowledge_workbench.application.sagas.run_source_ingestion_first_phase import (
    CreateSourceUnitsForIngestionPort,
    PersistAcceptedSourceIngestionPlanPort,
    RunSourceIngestionFirstPhase,
    RunSourceIngestionFirstPhaseCommand,
    RunSourceIngestionFirstPhaseResult,
    RunSourceIngestionFirstPhaseStatus,
    StartSourceIngestionWorkflowPort,
)
from src.contexts.knowledge_workbench.application.sagas.source_ingestion_admission import (
    SourceIngestionActor,
    SourceIngestionAdmissionDecision,
    SourceIngestionAdmissionStatus,
)
from src.contexts.knowledge_workbench.application.sagas.start_source_ingestion_workflow import (
    SourceIngestionAcceptedPlan,
    StartSourceIngestionWorkflowCommand,
    StartSourceIngestionWorkflowResult,
    StartSourceIngestionWorkflowStatus,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_saga_state import (
    KnowledgeExtractionPhaseStatus,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_format import (
    SourceFormat,
)


class FakeStarter:
    def __init__(self, *, result: StartSourceIngestionWorkflowResult) -> None:
        self.result = result
        self.commands: list[StartSourceIngestionWorkflowCommand] = []

    async def execute(
        self,
        command: StartSourceIngestionWorkflowCommand,
    ) -> StartSourceIngestionWorkflowResult:
        self.commands.append(command)
        return self.result


class FakeDocumentPersister:
    def __init__(
        self,
        *,
        result: PersistAcceptedSourceIngestionPlanResult,
        fail: bool = False,
    ) -> None:
        self.result = result
        self.fail = fail
        self.commands: list[PersistAcceptedSourceIngestionPlanCommand] = []

    async def execute(
        self,
        command: PersistAcceptedSourceIngestionPlanCommand,
    ) -> PersistAcceptedSourceIngestionPlanResult:
        self.commands.append(command)
        if self.fail:
            raise RuntimeError("document persistence failed")
        return self.result


class FakeSourceUnitCreator:
    def __init__(
        self,
        *,
        result: CreateSourceUnitsForIngestionResult,
        fail: bool = False,
    ) -> None:
        self.result = result
        self.fail = fail
        self.commands: list[CreateSourceUnitsForIngestionCommand] = []

    async def execute(
        self,
        command: CreateSourceUnitsForIngestionCommand,
    ) -> CreateSourceUnitsForIngestionResult:
        self.commands.append(command)
        if self.fail:
            raise RuntimeError("source unit creation failed")
        return self.result


def _now() -> datetime:
    return datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)


def _actor() -> SourceIngestionActor:
    return SourceIngestionActor(actor_user_id="owner-1")


def _accepted_plan() -> SourceIngestionAcceptedPlan:
    return SourceIngestionAcceptedPlan(
        project_id="project-1",
        actor_user_id="owner-1",
        source_document_ref="source-document:project-1:abc",
        source_format=SourceFormat.MARKDOWN,
        content_hash="sha256:abc",
        original_filename="knowledge.md",
        occurred_at=_now(),
    )


def _allowed_admission() -> SourceIngestionAdmissionDecision:
    return SourceIngestionAdmissionDecision(
        project_id="project-1",
        actor_user_id="owner-1",
        status=SourceIngestionAdmissionStatus.ALLOWED,
        reason="project_role_allowed",
    )


def _denied_admission(
    status: SourceIngestionAdmissionStatus = (
        SourceIngestionAdmissionStatus.ACTOR_NOT_AUTHENTICATED
    ),
) -> SourceIngestionAdmissionDecision:
    return SourceIngestionAdmissionDecision(
        project_id="project-1",
        actor_user_id=None,
        status=status,
        reason="denied",
    )


def _start_accepted_result() -> StartSourceIngestionWorkflowResult:
    return StartSourceIngestionWorkflowResult(
        status=StartSourceIngestionWorkflowStatus.ACCEPTED,
        admission=_allowed_admission(),
        accepted_plan=_accepted_plan(),
    )


def _start_rejected_result(
    status: SourceIngestionAdmissionStatus = (
        SourceIngestionAdmissionStatus.ACTOR_NOT_AUTHENTICATED
    ),
) -> StartSourceIngestionWorkflowResult:
    return StartSourceIngestionWorkflowResult(
        status=StartSourceIngestionWorkflowStatus.REJECTED,
        admission=_denied_admission(status),
    )


def _document_result() -> PersistAcceptedSourceIngestionPlanResult:
    return PersistAcceptedSourceIngestionPlanResult(
        workflow_run_id="knowledge-extraction:source-document:project-1:abc",
        source_document_ref="source-document:project-1:abc",
        document_checkpoint_status=KnowledgeExtractionPhaseStatus.COMPLETED,
        source_document_persisted=True,
    )


def _source_units_result() -> CreateSourceUnitsForIngestionResult:
    return CreateSourceUnitsForIngestionResult(
        workflow_run_id="knowledge-extraction:source-document:project-1:abc",
        source_document_ref="source-document:project-1:abc",
        source_unit_count=3,
        source_units_checkpoint_status=KnowledgeExtractionPhaseStatus.COMPLETED,
    )


def _command(
    *,
    project_id: str = "project-1",
    content_bytes: bytes = b"# Knowledge",
    raw_text: str = "# Knowledge\n\nText",
    occurred_at: datetime | None = None,
) -> RunSourceIngestionFirstPhaseCommand:
    return RunSourceIngestionFirstPhaseCommand(
        project_id=project_id,
        actor=_actor(),
        original_filename="knowledge.md",
        source_format=SourceFormat.MARKDOWN,
        content_bytes=content_bytes,
        raw_text=raw_text,
        occurred_at=occurred_at or _now(),
    )


def _use_case(
    *,
    starter: FakeStarter,
    document_persister: FakeDocumentPersister,
    source_unit_creator: FakeSourceUnitCreator,
) -> RunSourceIngestionFirstPhase:
    starter_port: StartSourceIngestionWorkflowPort = starter
    document_persister_port: PersistAcceptedSourceIngestionPlanPort = document_persister
    source_unit_creator_port: CreateSourceUnitsForIngestionPort = source_unit_creator
    return RunSourceIngestionFirstPhase(
        starter=starter_port,
        document_persister=document_persister_port,
        source_unit_creator=source_unit_creator_port,
    )


@pytest.mark.asyncio
async def test_rejected_admission_stops_immediately() -> None:
    starter = FakeStarter(
        result=_start_rejected_result(
            SourceIngestionAdmissionStatus.ACTOR_ROLE_NOT_ALLOWED,
        ),
    )
    document_persister = FakeDocumentPersister(result=_document_result())
    source_unit_creator = FakeSourceUnitCreator(result=_source_units_result())

    result = await _use_case(
        starter=starter,
        document_persister=document_persister,
        source_unit_creator=source_unit_creator,
    ).execute(_command())

    assert result.status is RunSourceIngestionFirstPhaseStatus.REJECTED
    assert (
        result.admission_status is SourceIngestionAdmissionStatus.ACTOR_ROLE_NOT_ALLOWED
    )
    assert len(starter.commands) == 1
    assert document_persister.commands == []
    assert source_unit_creator.commands == []


@pytest.mark.asyncio
async def test_accepted_path_calls_all_steps_in_order() -> None:
    starter = FakeStarter(result=_start_accepted_result())
    document_persister = FakeDocumentPersister(result=_document_result())
    source_unit_creator = FakeSourceUnitCreator(result=_source_units_result())

    result = await _use_case(
        starter=starter,
        document_persister=document_persister,
        source_unit_creator=source_unit_creator,
    ).execute(_command())

    assert len(starter.commands) == 1
    assert len(document_persister.commands) == 1
    assert document_persister.commands[0].accepted_plan == _accepted_plan()
    assert len(source_unit_creator.commands) == 1
    assert source_unit_creator.commands[0].workflow_run_id == (
        _document_result().workflow_run_id
    )
    assert source_unit_creator.commands[0].source_document_ref == (
        _document_result().source_document_ref
    )
    assert result.status is RunSourceIngestionFirstPhaseStatus.COMPLETED
    assert result.admission_status is SourceIngestionAdmissionStatus.ALLOWED
    assert result.workflow_run_id == _document_result().workflow_run_id
    assert result.source_document_ref == _document_result().source_document_ref
    assert result.source_unit_count == _source_units_result().source_unit_count


@pytest.mark.asyncio
async def test_raw_text_passed_only_to_source_unit_creator() -> None:
    starter = FakeStarter(result=_start_accepted_result())
    document_persister = FakeDocumentPersister(result=_document_result())
    source_unit_creator = FakeSourceUnitCreator(result=_source_units_result())
    command = _command(content_bytes=b"binary-ish bytes", raw_text="Raw text only")

    await _use_case(
        starter=starter,
        document_persister=document_persister,
        source_unit_creator=source_unit_creator,
    ).execute(command)

    assert starter.commands[0].content_bytes == b"binary-ish bytes"
    assert source_unit_creator.commands[0].raw_text == "Raw text only"


@pytest.mark.asyncio
async def test_document_persister_exception_propagates_and_units_not_called() -> None:
    starter = FakeStarter(result=_start_accepted_result())
    document_persister = FakeDocumentPersister(
        result=_document_result(),
        fail=True,
    )
    source_unit_creator = FakeSourceUnitCreator(result=_source_units_result())

    with pytest.raises(RuntimeError, match="document persistence failed"):
        await _use_case(
            starter=starter,
            document_persister=document_persister,
            source_unit_creator=source_unit_creator,
        ).execute(_command())

    assert len(document_persister.commands) == 1
    assert source_unit_creator.commands == []


@pytest.mark.asyncio
async def test_source_unit_creator_exception_propagates() -> None:
    starter = FakeStarter(result=_start_accepted_result())
    document_persister = FakeDocumentPersister(result=_document_result())
    source_unit_creator = FakeSourceUnitCreator(
        result=_source_units_result(),
        fail=True,
    )

    with pytest.raises(RuntimeError, match="source unit creation failed"):
        await _use_case(
            starter=starter,
            document_persister=document_persister,
            source_unit_creator=source_unit_creator,
        ).execute(_command())

    assert len(source_unit_creator.commands) == 1


def test_validation_rejects_bad_command_shapes() -> None:
    with pytest.raises(ValueError, match="project_id must be non-empty"):
        _command(project_id=" ")

    with pytest.raises(ValueError, match="content_bytes must be non-empty"):
        _command(content_bytes=b"")

    with pytest.raises(ValueError, match="raw_text must be non-empty"):
        _command(raw_text=" ")

    with pytest.raises(ValueError, match="occurred_at must be timezone-aware"):
        _command(occurred_at=datetime(2026, 6, 10, 12, 0))


def test_validation_rejects_bad_result_shapes() -> None:
    with pytest.raises(ValueError, match="workflow_run_id must be non-empty"):
        RunSourceIngestionFirstPhaseResult(
            status=RunSourceIngestionFirstPhaseStatus.COMPLETED,
            admission_status=SourceIngestionAdmissionStatus.ALLOWED,
            workflow_run_id=None,
            source_document_ref="source-document:project-1:abc",
            source_unit_count=3,
        )

    with pytest.raises(ValueError, match="source_document_ref must be non-empty"):
        RunSourceIngestionFirstPhaseResult(
            status=RunSourceIngestionFirstPhaseStatus.COMPLETED,
            admission_status=SourceIngestionAdmissionStatus.ALLOWED,
            workflow_run_id="workflow-1",
            source_document_ref=None,
            source_unit_count=3,
        )

    with pytest.raises(ValueError, match="completed result requires"):
        RunSourceIngestionFirstPhaseResult(
            status=RunSourceIngestionFirstPhaseStatus.COMPLETED,
            admission_status=SourceIngestionAdmissionStatus.ALLOWED,
            workflow_run_id="workflow-1",
            source_document_ref="source-document:project-1:abc",
            source_unit_count=0,
        )

    with pytest.raises(ValueError, match="rejected result must not include"):
        RunSourceIngestionFirstPhaseResult(
            status=RunSourceIngestionFirstPhaseStatus.REJECTED,
            admission_status=SourceIngestionAdmissionStatus.ACTOR_ROLE_NOT_ALLOWED,
            workflow_run_id="workflow-1",
            source_document_ref=None,
            source_unit_count=0,
        )

    with pytest.raises(ValueError, match="rejected result must not include"):
        RunSourceIngestionFirstPhaseResult(
            status=RunSourceIngestionFirstPhaseStatus.REJECTED,
            admission_status=SourceIngestionAdmissionStatus.ACTOR_ROLE_NOT_ALLOWED,
            workflow_run_id=None,
            source_document_ref="source-document:project-1:abc",
            source_unit_count=0,
        )

    with pytest.raises(ValueError, match="rejected result requires"):
        RunSourceIngestionFirstPhaseResult(
            status=RunSourceIngestionFirstPhaseStatus.REJECTED,
            admission_status=SourceIngestionAdmissionStatus.ACTOR_ROLE_NOT_ALLOWED,
            workflow_run_id=None,
            source_document_ref=None,
            source_unit_count=1,
        )

    with pytest.raises(
        TypeError, match="status must be RunSourceIngestionFirstPhaseStatus"
    ):
        RunSourceIngestionFirstPhaseResult(
            status=cast(RunSourceIngestionFirstPhaseStatus, "COMPLETED"),
            admission_status=SourceIngestionAdmissionStatus.ALLOWED,
            workflow_run_id="workflow-1",
            source_document_ref="source-document:project-1:abc",
            source_unit_count=3,
        )


def test_run_source_ingestion_first_phase_source_guard() -> None:
    source = Path(
        "src/contexts/knowledge_workbench/application/sagas/"
        "run_source_ingestion_first_phase.py",
    ).read_text(encoding="utf-8")

    required_markers = [
        "RunSourceIngestionFirstPhase",
        "RunSourceIngestionFirstPhaseCommand",
        "RunSourceIngestionFirstPhaseResult",
        "RunSourceIngestionFirstPhaseStatus",
        "StartSourceIngestionWorkflowCommand",
        "PersistAcceptedSourceIngestionPlanCommand",
        "CreateSourceUnitsForIngestionCommand",
        "COMPLETED",
        "REJECTED",
    ]
    forbidden_markers = [
        "fastapi",
        "HTTPException",
        "Depends",
        "Header",
        "Request",
        "src.interfaces",
        "src.infrastructure",
        "asyncpg",
        "postgres",
        "Postgres",
        "UserRepository",
        "ProjectRepository",
        "get_current_user_id",
        "SourceParserPort",
        "RunClaimExtractionStageAsync",
        "DraftObservationExtractionSchedulingReconciler",
        "PROMPT_A",
        "capacity_runtime",
        "execution_runtime",
        "llm_runtime",
        "artifact_runtime",
        "worker_loop",
        "JobDispatcher",
        "outbox_events",
        "queue",
        "Queue",
        "pdf",
        "Pdf",
        "openpyxl",
        "pandas",
        "markdown",
        "BeautifulSoup",
        "save_source_document",
        "save_source_units",
        "save_workflow_state",
        "save_phase_checkpoint",
        "emit_command",
        "record_command",
        "event_was_processed",
        "record_processed_event",
    ]

    for marker in required_markers:
        assert marker in source

    for marker in forbidden_markers:
        assert marker not in source
