from __future__ import annotations

from src.application.services.faq_workbench_parallel_processing_coordinator_service import (
    RunParallelWorkbenchProcessingCommand,
)


def test_parallel_processing_command_defaults_to_four_section_workers() -> None:
    command = RunParallelWorkbenchProcessingCommand(
        project_id="project-1",
        document_id="document-1",
        processing_run_id="processing-run-1",
    )

    assert command.section_worker_count == 4
