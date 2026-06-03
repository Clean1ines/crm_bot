from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping

from src.domain.project_plane.knowledge_workbench import (
    DomainInvariantError,
    ProcessingMethod,
    ProcessingTrigger,
)


class WorkbenchProcessDocumentJobPayloadError(ValueError):
    pass


class WorkbenchProcessDocumentJobSource(StrEnum):
    FRESH_UPLOAD = "workbench_fresh_upload"
    EXPLICIT_USER_RESUME = "workbench_explicit_user_resume"
    QUOTA_RECOVERY = "workbench_quota_recovery"
    PROVIDER_RECOVERY = "workbench_provider_recovery"
    SERVER_RECOVERY = "workbench_server_recovery"
    MANUAL_REPROCESS = "workbench_manual_reprocess"


@dataclass(frozen=True, slots=True)
class WorkbenchProcessDocumentJobPayloadDto:
    project_id: str
    document_id: str
    processing_run_id: str
    processing_method: ProcessingMethod
    trigger: ProcessingTrigger
    source: WorkbenchProcessDocumentJobSource

    @classmethod
    def fresh_upload(
        cls,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
    ) -> WorkbenchProcessDocumentJobPayloadDto:
        return cls(
            project_id=project_id,
            document_id=document_id,
            processing_run_id=processing_run_id,
            processing_method=ProcessingMethod.FAQ_SECTION_REGISTRY_V1,
            trigger=ProcessingTrigger.FRESH_UPLOAD,
            source=WorkbenchProcessDocumentJobSource.FRESH_UPLOAD,
        )

    @classmethod
    def explicit_user_resume(
        cls,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
    ) -> WorkbenchProcessDocumentJobPayloadDto:
        return cls(
            project_id=project_id,
            document_id=document_id,
            processing_run_id=processing_run_id,
            processing_method=ProcessingMethod.FAQ_SECTION_REGISTRY_V1,
            trigger=ProcessingTrigger.EXPLICIT_USER_RESUME,
            source=WorkbenchProcessDocumentJobSource.EXPLICIT_USER_RESUME,
        )

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, object],
    ) -> WorkbenchProcessDocumentJobPayloadDto:
        allowed_keys = {
            "project_id",
            "document_id",
            "processing_run_id",
            "processing_method",
            "trigger",
            "source",
        }
        unknown_keys = set(payload).difference(allowed_keys)
        if unknown_keys:
            names = ", ".join(sorted(str(key) for key in unknown_keys))
            raise WorkbenchProcessDocumentJobPayloadError(
                f"workbench process payload has unsupported fields: {names}"
            )

        project_id = str(payload.get("project_id") or "").strip()
        document_id = str(payload.get("document_id") or "").strip()
        processing_run_id = str(payload.get("processing_run_id") or "").strip()
        raw_processing_method = str(payload.get("processing_method") or "").strip()
        raw_trigger = str(payload.get("trigger") or "").strip()
        raw_source = str(payload.get("source") or "").strip()

        if not project_id:
            raise WorkbenchProcessDocumentJobPayloadError(
                "workbench process payload missing project_id"
            )
        if not document_id:
            raise WorkbenchProcessDocumentJobPayloadError(
                "workbench process payload missing document_id"
            )
        if not processing_run_id:
            raise WorkbenchProcessDocumentJobPayloadError(
                "workbench process payload missing processing_run_id"
            )

        try:
            processing_method = ProcessingMethod(raw_processing_method)
        except ValueError as exc:
            raise WorkbenchProcessDocumentJobPayloadError(
                f"unsupported workbench processing_method: {raw_processing_method}"
            ) from exc

        try:
            trigger = ProcessingTrigger(raw_trigger)
        except ValueError as exc:
            raise WorkbenchProcessDocumentJobPayloadError(
                f"unsupported workbench trigger: {raw_trigger}"
            ) from exc

        try:
            source = WorkbenchProcessDocumentJobSource(raw_source)
        except ValueError as exc:
            raise WorkbenchProcessDocumentJobPayloadError(
                f"unsupported workbench source: {raw_source}"
            ) from exc

        dto = cls(
            project_id=project_id,
            document_id=document_id,
            processing_run_id=processing_run_id,
            processing_method=processing_method,
            trigger=trigger,
            source=source,
        )
        try:
            dto._validate()
        except DomainInvariantError as exc:
            raise WorkbenchProcessDocumentJobPayloadError(str(exc)) from exc
        return dto

    def to_queue_payload(self) -> dict[str, object]:
        self._validate()
        return {
            "project_id": self.project_id,
            "document_id": self.document_id,
            "processing_run_id": self.processing_run_id,
            "processing_method": self.processing_method.value,
            "trigger": self.trigger.value,
            "source": self.source.value,
        }

    def _validate(self) -> None:
        if not self.project_id.strip():
            raise DomainInvariantError("project_id is required")
        if not self.document_id.strip():
            raise DomainInvariantError("document_id is required")
        if not self.processing_run_id.strip():
            raise DomainInvariantError("processing_run_id is required")
        if self.processing_method is not ProcessingMethod.FAQ_SECTION_REGISTRY_V1:
            raise DomainInvariantError(
                "workbench process document v1 supports only faq_section_registry_v1"
            )
