from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from src.application.ports.workbench_observability import WorkbenchProgressQueryPort
from src.application.workbench_observability.tombstone import (
    is_deleted_workbench_document,
)


class WorkbenchProgressNotFoundError(LookupError):
    pass


KNOWN_SECTION_STATUSES: Final[tuple[str, ...]] = (
    "pending",
    "running",
    "completed",
    "failed",
    "cancelled",
    "deleted",
)

CANCELLABLE_RUN_STATUSES: Final[frozenset[str]] = frozenset(
    {"pending", "running", "cancelling"}
)
MANUAL_RESUME_RUN_STATUSES: Final[frozenset[str]] = frozenset({"cancelled_by_user"})
AUTO_RECOVERY_RUN_STATUSES: Final[frozenset[str]] = frozenset(
    {"paused_quota", "paused_provider", "paused_server_interrupted"}
)


@dataclass(frozen=True, slots=True)
class WorkbenchProgressReadModel:
    document: dict[str, object]
    processing_run: dict[str, object] | None
    section_status_counts: dict[str, int]
    node_runs: tuple[dict[str, object], ...]

    def to_dict(self) -> dict[str, object]:
        progress = _build_progress(self.section_status_counts)
        actions = _build_actions(
            document=self.document,
            processing_run=self.processing_run,
            section_status_counts=self.section_status_counts,
            node_runs=self.node_runs,
        )
        return {
            "document": self.document,
            "processing_run": self.processing_run,
            "section_status_counts": self.section_status_counts,
            "node_runs": list(self.node_runs),
            "progress": progress,
            "actions": actions,
        }


class WorkbenchProgressReadService:
    def __init__(self, query_port: WorkbenchProgressQueryPort) -> None:
        self._query_port = query_port

    async def get_progress(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> dict[str, object]:
        document = await self._query_port.fetch_document(
            project_id=project_id,
            document_id=document_id,
        )
        if document is None or is_deleted_workbench_document(document):
            raise WorkbenchProgressNotFoundError("Knowledge document not found")

        processing_run = await self._query_port.fetch_latest_processing_run(
            project_id=project_id,
            document_id=document_id,
        )
        section_status_counts = await self._query_port.fetch_section_status_counts(
            project_id=project_id,
            document_id=document_id,
        )

        node_runs: tuple[Mapping[str, object], ...] = ()
        if processing_run is not None:
            processing_run_id = str(processing_run.get("processing_run_id") or "")
            if processing_run_id:
                node_runs = await self._query_port.fetch_node_runs(
                    project_id=project_id,
                    document_id=document_id,
                    processing_run_id=processing_run_id,
                )

        return build_workbench_progress_payload(
            document=document,
            processing_run=processing_run,
            section_status_counts=section_status_counts,
            node_runs=node_runs,
        )


def build_workbench_progress_payload(
    *,
    document: Mapping[str, object] | None,
    processing_run: Mapping[str, object] | None,
    section_status_counts: Mapping[str, int],
    node_runs: tuple[Mapping[str, object], ...],
) -> dict[str, object]:
    read_model = build_workbench_progress_read_model(
        document=document,
        processing_run=processing_run,
        section_status_counts=section_status_counts,
        node_runs=node_runs,
    )
    return read_model.to_dict()


def build_workbench_progress_read_model(
    *,
    document: Mapping[str, object] | None,
    processing_run: Mapping[str, object] | None,
    section_status_counts: Mapping[str, int],
    node_runs: tuple[Mapping[str, object], ...],
) -> WorkbenchProgressReadModel:
    if document is None:
        raise WorkbenchProgressNotFoundError("Knowledge document not found")

    return WorkbenchProgressReadModel(
        document=dict(document),
        processing_run=dict(processing_run) if processing_run is not None else None,
        section_status_counts=_normalize_section_status_counts(section_status_counts),
        node_runs=tuple(dict(row) for row in node_runs),
    )


def _normalize_section_status_counts(
    raw_counts: Mapping[str, int],
) -> dict[str, int]:
    counts = {status: 0 for status in KNOWN_SECTION_STATUSES}
    for raw_status, raw_count in raw_counts.items():
        counts[str(raw_status)] = int(raw_count)
    return counts


def _build_progress(section_status_counts: Mapping[str, int]) -> dict[str, object]:
    total_sections = sum(int(value) for value in section_status_counts.values())
    completed_sections = int(section_status_counts.get("completed", 0))
    failed_sections = int(section_status_counts.get("failed", 0))
    cancelled_sections = int(section_status_counts.get("cancelled", 0))

    percent = 0.0
    if total_sections > 0:
        percent = round((completed_sections / total_sections) * 100, 1)

    return {
        "total_sections": total_sections,
        "completed_sections": completed_sections,
        "failed_sections": failed_sections,
        "cancelled_sections": cancelled_sections,
        "percent": percent,
    }


def _build_actions(
    *,
    document: Mapping[str, object],
    processing_run: Mapping[str, object] | None,
    section_status_counts: Mapping[str, int],
    node_runs: tuple[Mapping[str, object], ...],
) -> dict[str, object]:
    document_status = str(document.get("status") or "")
    run_status = (
        str(processing_run.get("status") or "") if processing_run is not None else ""
    )

    has_failed_sections = int(section_status_counts.get("failed", 0)) > 0
    has_failed_nodes = any(
        str(row.get("status") or "") == "failed" for row in node_runs
    )
    can_retry_failed = has_failed_sections or has_failed_nodes

    return {
        "can_cancel": run_status in CANCELLABLE_RUN_STATUSES
        or document_status in {"processing", "sectioned"},
        "can_resume": run_status in MANUAL_RESUME_RUN_STATUSES,
        "can_auto_recover": run_status in AUTO_RECOVERY_RUN_STATUSES,
        "can_retry_failed": can_retry_failed,
        "can_publish": run_status == "completed" and not can_retry_failed,
    }
