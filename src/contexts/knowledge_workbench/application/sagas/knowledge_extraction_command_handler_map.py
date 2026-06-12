from __future__ import annotations

from dataclasses import dataclass

from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalCommandType,
)


@dataclass(frozen=True, slots=True)
class KnowledgeExtractionImplementedCommandHandler:
    command_type: KnowledgeExtractionCanonicalCommandType
    handler_name: str

    def __post_init__(self) -> None:
        if not isinstance(self.command_type, KnowledgeExtractionCanonicalCommandType):
            raise TypeError(
                "command_type must be KnowledgeExtractionCanonicalCommandType"
            )
        if not isinstance(self.handler_name, str) or not self.handler_name.strip():
            raise ValueError("handler_name must be non-empty")


IMPLEMENTED_KNOWLEDGE_EXTRACTION_COMMAND_HANDLERS = (
    KnowledgeExtractionImplementedCommandHandler(
        command_type=(
            KnowledgeExtractionCanonicalCommandType.SCHEDULE_CLAIM_BUILDER_SECTION_WORK
        ),
        handler_name="HandleScheduleClaimBuilderSectionWorkCommandHandler",
    ),
    KnowledgeExtractionImplementedCommandHandler(
        command_type=(
            KnowledgeExtractionCanonicalCommandType.PREPARE_CLAIM_BUILDER_DISPATCH_BATCH
        ),
        handler_name="HandlePrepareClaimBuilderDispatchBatchCommandHandler",
    ),
    KnowledgeExtractionImplementedCommandHandler(
        command_type=(
            KnowledgeExtractionCanonicalCommandType.EXECUTE_CLAIM_BUILDER_SECTION
        ),
        handler_name="HandleExecuteClaimBuilderSectionCommandHandler",
    ),
)


def is_command_implemented(
    command_type: KnowledgeExtractionCanonicalCommandType,
) -> bool:
    return implemented_handler_name_for(command_type) is not None


def implemented_handler_name_for(
    command_type: KnowledgeExtractionCanonicalCommandType,
) -> str | None:
    for handler in IMPLEMENTED_KNOWLEDGE_EXTRACTION_COMMAND_HANDLERS:
        if handler.command_type is command_type:
            return handler.handler_name
    return None
