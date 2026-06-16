from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256

from src.contexts.knowledge_workbench.application.sagas.source_ingestion_admission import (
    SourceIngestionActor,
    SourceIngestionAdmissionDecision,
    SourceIngestionAdmissionPolicy,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_document_ref import (
    SourceDocumentRef,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_format import (
    SourceFormat,
)


class StartSourceIngestionWorkflowStatus(StrEnum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


@dataclass(frozen=True, slots=True)
class StartSourceIngestionWorkflowCommand:
    project_id: str
    actor: SourceIngestionActor
    original_filename: str | None
    source_format: SourceFormat
    content_bytes: bytes
    occurred_at: datetime

    def __post_init__(self) -> None:
        _require_non_empty_text(self.project_id, field_name="project_id")
        if not isinstance(self.actor, SourceIngestionActor):
            raise TypeError("actor must be SourceIngestionActor")
        _require_source_format(self.source_format)
        _require_non_empty_bytes(self.content_bytes, field_name="content_bytes")
        if self.original_filename is not None:
            _require_non_empty_text(
                self.original_filename,
                field_name="original_filename",
            )
        _require_timezone_aware(self.occurred_at, field_name="occurred_at")


@dataclass(frozen=True, slots=True)
class SourceIngestionAcceptedPlan:
    project_id: str
    actor_user_id: str
    source_document_ref: str
    source_format: SourceFormat
    content_hash: str
    original_filename: str | None
    occurred_at: datetime
    content_size_bytes: int = 0

    def __post_init__(self) -> None:
        _require_non_empty_text(self.project_id, field_name="project_id")
        _require_non_empty_text(self.actor_user_id, field_name="actor_user_id")
        _require_non_empty_text(
            self.source_document_ref,
            field_name="source_document_ref",
        )
        _require_source_format(self.source_format)
        _require_non_empty_text(self.content_hash, field_name="content_hash")
        if not self.content_hash.startswith("sha256:"):
            raise ValueError("content_hash must start with sha256:")
        if self.original_filename is not None:
            _require_non_empty_text(
                self.original_filename,
                field_name="original_filename",
            )
        _require_timezone_aware(self.occurred_at, field_name="occurred_at")


@dataclass(frozen=True, slots=True)
class StartSourceIngestionWorkflowResult:
    status: StartSourceIngestionWorkflowStatus
    admission: SourceIngestionAdmissionDecision
    accepted_plan: SourceIngestionAcceptedPlan | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, StartSourceIngestionWorkflowStatus):
            raise TypeError("status must be StartSourceIngestionWorkflowStatus")
        if not isinstance(self.admission, SourceIngestionAdmissionDecision):
            raise TypeError("admission must be SourceIngestionAdmissionDecision")
        if self.accepted_plan is not None and not isinstance(
            self.accepted_plan,
            SourceIngestionAcceptedPlan,
        ):
            raise TypeError("accepted_plan must be SourceIngestionAcceptedPlan")

        if self.status is StartSourceIngestionWorkflowStatus.ACCEPTED:
            if self.accepted_plan is None:
                raise ValueError("accepted result requires accepted_plan")
            if not self.admission.is_allowed():
                raise ValueError("accepted result requires allowed admission")
            return

        if self.accepted_plan is not None:
            raise ValueError("rejected result must not include accepted_plan")
        if self.admission.is_allowed():
            raise ValueError("rejected result requires denied admission")


class StartSourceIngestionWorkflow:
    def __init__(self, *, admission_policy: SourceIngestionAdmissionPolicy) -> None:
        self._admission_policy = admission_policy

    async def execute(
        self,
        command: StartSourceIngestionWorkflowCommand,
    ) -> StartSourceIngestionWorkflowResult:
        admission = await self._admission_policy.decide(
            project_id=command.project_id,
            actor=command.actor,
        )

        if not admission.is_allowed():
            return StartSourceIngestionWorkflowResult(
                status=StartSourceIngestionWorkflowStatus.REJECTED,
                admission=admission,
            )

        actor_user_id = admission.actor_user_id
        if actor_user_id is None:
            raise ValueError("allowed admission must include actor_user_id")

        content_hash_hex = sha256(command.content_bytes).hexdigest()
        content_hash = f"sha256:{content_hash_hex}"
        source_document_ref = _build_source_document_ref(
            project_id=command.project_id,
            content_hash_hex=content_hash_hex,
        )

        return StartSourceIngestionWorkflowResult(
            status=StartSourceIngestionWorkflowStatus.ACCEPTED,
            admission=admission,
            accepted_plan=SourceIngestionAcceptedPlan(
                project_id=command.project_id,
                actor_user_id=actor_user_id,
                source_document_ref=source_document_ref,
                source_format=command.source_format,
                content_hash=content_hash,
                original_filename=command.original_filename,
                occurred_at=command.occurred_at,
                content_size_bytes=len(command.content_bytes),
            ),
        )


def _build_source_document_ref(*, project_id: str, content_hash_hex: str) -> str:
    return SourceDocumentRef(
        value=f"source-document:{project_id}:{content_hash_hex}",
    ).value


def _require_non_empty_text(value: str, *, field_name: str) -> None:
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


def _require_source_format(value: SourceFormat) -> None:
    if not isinstance(value, SourceFormat):
        raise TypeError("source_format must be SourceFormat")
