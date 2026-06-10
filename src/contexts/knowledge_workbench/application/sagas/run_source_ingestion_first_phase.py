from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from src.contexts.knowledge_workbench.application.sagas.create_source_units_for_ingestion import (
    CreateSourceUnitsForIngestionCommand,
    CreateSourceUnitsForIngestionResult,
)
from src.contexts.knowledge_workbench.application.sagas.persist_accepted_source_ingestion_plan import (
    PersistAcceptedSourceIngestionPlanCommand,
    PersistAcceptedSourceIngestionPlanResult,
)
from src.contexts.knowledge_workbench.application.sagas.source_ingestion_admission import (
    SourceIngestionActor,
    SourceIngestionAdmissionStatus,
)
from src.contexts.knowledge_workbench.application.sagas.start_source_ingestion_workflow import (
    StartSourceIngestionWorkflowCommand,
    StartSourceIngestionWorkflowResult,
    StartSourceIngestionWorkflowStatus,
)
from src.contexts.knowledge_workbench.document_segmentation.domain import (
    DocumentSegmentationBudget,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_format import (
    SourceFormat,
)


class StartSourceIngestionWorkflowPort(Protocol):
    async def execute(
        self,
        command: StartSourceIngestionWorkflowCommand,
    ) -> StartSourceIngestionWorkflowResult: ...


class PersistAcceptedSourceIngestionPlanPort(Protocol):
    async def execute(
        self,
        command: PersistAcceptedSourceIngestionPlanCommand,
    ) -> PersistAcceptedSourceIngestionPlanResult: ...


class CreateSourceUnitsForIngestionPort(Protocol):
    async def execute(
        self,
        command: CreateSourceUnitsForIngestionCommand,
    ) -> CreateSourceUnitsForIngestionResult: ...


class RunSourceIngestionFirstPhaseStatus(StrEnum):
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"


@dataclass(frozen=True, slots=True)
class RunSourceIngestionFirstPhaseCommand:
    project_id: str
    actor: SourceIngestionActor
    original_filename: str | None
    source_format: SourceFormat
    content_bytes: bytes
    raw_text: str
    occurred_at: datetime
    segmentation_budget: DocumentSegmentationBudget | None = None

    def __post_init__(self) -> None:
        _require_non_empty_text(self.project_id, field_name="project_id")
        if not isinstance(self.actor, SourceIngestionActor):
            raise TypeError("actor must be SourceIngestionActor")
        if self.original_filename is not None:
            _require_non_empty_text(
                self.original_filename,
                field_name="original_filename",
            )
        if not isinstance(self.source_format, SourceFormat):
            raise TypeError("source_format must be SourceFormat")
        _require_non_empty_bytes(self.content_bytes, field_name="content_bytes")
        _require_non_empty_text(self.raw_text, field_name="raw_text")
        _require_timezone_aware(self.occurred_at, field_name="occurred_at")
        if self.segmentation_budget is not None and not isinstance(
            self.segmentation_budget,
            DocumentSegmentationBudget,
        ):
            raise TypeError("segmentation_budget must be DocumentSegmentationBudget")


@dataclass(frozen=True, slots=True)
class RunSourceIngestionFirstPhaseResult:
    status: RunSourceIngestionFirstPhaseStatus
    admission_status: SourceIngestionAdmissionStatus
    workflow_run_id: str | None = None
    source_document_ref: str | None = None
    source_unit_count: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.status, RunSourceIngestionFirstPhaseStatus):
            raise TypeError("status must be RunSourceIngestionFirstPhaseStatus")
        if not isinstance(self.admission_status, SourceIngestionAdmissionStatus):
            raise TypeError("admission_status must be SourceIngestionAdmissionStatus")
        if not isinstance(self.source_unit_count, int):
            raise TypeError("source_unit_count must be int")

        if self.status is RunSourceIngestionFirstPhaseStatus.COMPLETED:
            _require_non_empty_text(
                self.workflow_run_id,
                field_name="workflow_run_id",
            )
            _require_non_empty_text(
                self.source_document_ref,
                field_name="source_document_ref",
            )
            if self.source_unit_count <= 0:
                raise ValueError("completed result requires source_unit_count > 0")
            return

        if self.workflow_run_id is not None:
            raise ValueError("rejected result must not include workflow_run_id")
        if self.source_document_ref is not None:
            raise ValueError("rejected result must not include source_document_ref")
        if self.source_unit_count != 0:
            raise ValueError("rejected result requires source_unit_count == 0")


class RunSourceIngestionFirstPhase:
    def __init__(
        self,
        *,
        starter: StartSourceIngestionWorkflowPort,
        document_persister: PersistAcceptedSourceIngestionPlanPort,
        source_unit_creator: CreateSourceUnitsForIngestionPort,
    ) -> None:
        self._starter = starter
        self._document_persister = document_persister
        self._source_unit_creator = source_unit_creator

    async def execute(
        self,
        command: RunSourceIngestionFirstPhaseCommand,
    ) -> RunSourceIngestionFirstPhaseResult:
        start_result = await self._starter.execute(
            StartSourceIngestionWorkflowCommand(
                project_id=command.project_id,
                actor=command.actor,
                original_filename=command.original_filename,
                source_format=command.source_format,
                content_bytes=command.content_bytes,
                occurred_at=command.occurred_at,
            ),
        )

        if start_result.status is StartSourceIngestionWorkflowStatus.REJECTED:
            return RunSourceIngestionFirstPhaseResult(
                status=RunSourceIngestionFirstPhaseStatus.REJECTED,
                admission_status=start_result.admission.status,
            )

        accepted_plan = start_result.accepted_plan
        if accepted_plan is None:
            raise ValueError("accepted start result requires accepted_plan")

        document_result = await self._document_persister.execute(
            PersistAcceptedSourceIngestionPlanCommand(
                accepted_plan=accepted_plan,
            ),
        )

        source_units_result = await self._source_unit_creator.execute(
            CreateSourceUnitsForIngestionCommand(
                workflow_run_id=document_result.workflow_run_id,
                project_id=command.project_id,
                source_document_ref=document_result.source_document_ref,
                raw_text=command.raw_text,
                occurred_at=command.occurred_at,
                segmentation_budget=command.segmentation_budget,
            ),
        )

        return RunSourceIngestionFirstPhaseResult(
            status=RunSourceIngestionFirstPhaseStatus.COMPLETED,
            admission_status=SourceIngestionAdmissionStatus.ALLOWED,
            workflow_run_id=document_result.workflow_run_id,
            source_document_ref=document_result.source_document_ref,
            source_unit_count=source_units_result.source_unit_count,
        )


def _require_non_empty_text(value: str | None, *, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _require_non_empty_bytes(value: bytes, *, field_name: str) -> None:
    if not isinstance(value, bytes):
        raise TypeError(f"{field_name} must be bytes")
    if not value:
        raise ValueError(f"{field_name} must be non-empty")


def _require_timezone_aware(value: datetime, *, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
