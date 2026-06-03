from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from src.infrastructure.queue.job_exceptions import PermanentJobError


@dataclass(frozen=True, slots=True)
class LegacyWorkbenchDocumentJobPayload:
    project_id: str
    document_id: str
    processing_run_id: str

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, object],
    ) -> LegacyWorkbenchDocumentJobPayload:
        return cls(
            project_id=_required_text(payload, "project_id"),
            document_id=_required_text(payload, "document_id"),
            processing_run_id=_required_text(payload, "processing_run_id"),
        )


async def handle_process_workbench_document(
    job,
    *,
    connection=None,
) -> None:
    """Reject the retired sequential FAQ Workbench document processor.

    Production uploads now enqueue the parallel Workbench processor. This handler
    remains only so stale queued jobs fail explicitly instead of silently reviving
    the old surface/question/final-reconciliation graph.
    """

    payload = getattr(job, "payload", None)
    if isinstance(payload, Mapping):
        parsed = LegacyWorkbenchDocumentJobPayload.from_mapping(payload)
        raise PermanentJobError(
            "legacy process_workbench_document task is retired; "
            "use process_workbench_parallel_processing "
            f"for document_id={parsed.document_id}"
        )

    raise PermanentJobError(
        "legacy process_workbench_document task is retired; "
        "use process_workbench_parallel_processing"
    )


async def mark_process_workbench_document_exhausted(job) -> None:
    """Compatibility hook for old worker error handling.

    The old sequential task is permanently retired, so there is no recovery
    lifecycle to mutate here.
    """

    return None


def _required_text(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise PermanentJobError(f"legacy workbench document payload missing {key}")
    return value.strip()


__all__ = [
    "LegacyWorkbenchDocumentJobPayload",
    "handle_process_workbench_document",
    "mark_process_workbench_document_exhausted",
]
