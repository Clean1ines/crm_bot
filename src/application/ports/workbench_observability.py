from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol


class WorkbenchProgressQueryPort(Protocol):
    async def fetch_document(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> Mapping[str, object] | None: ...

    async def fetch_latest_processing_run(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> Mapping[str, object] | None: ...

    async def fetch_section_status_counts(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> Mapping[str, int]: ...

    async def fetch_node_runs(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
    ) -> tuple[Mapping[str, object], ...]: ...
