from __future__ import annotations

from dataclasses import dataclass


class RetiredSequentialWorkbenchOrchestratorError(RuntimeError):
    """Raised when the retired sequential Workbench graph is invoked."""


@dataclass(frozen=True, slots=True)
class FaqWorkbenchDocumentProcessingResult:
    document_id: str
    processing_run_id: str
    processed: bool = False
    reason: str = "retired_sequential_orchestrator"


class FaqWorkbenchDocumentProcessingOrchestrator:
    """Retired compatibility shell.

    Production Workbench processing now runs through the parallel section queue:
    claim observations -> fact registry builder -> registry application.
    """

    async def process_existing_document(
        self, *args: object, **kwargs: object
    ) -> FaqWorkbenchDocumentProcessingResult:
        raise RetiredSequentialWorkbenchOrchestratorError(
            "Sequential FAQ Workbench orchestrator is retired; use parallel Workbench processing."
        )


__all__ = [
    "FaqWorkbenchDocumentProcessingOrchestrator",
    "FaqWorkbenchDocumentProcessingResult",
    "RetiredSequentialWorkbenchOrchestratorError",
]
