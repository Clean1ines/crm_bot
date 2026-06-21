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
            KnowledgeExtractionCanonicalCommandType.SPLIT_CLAIM_BUILDER_SOURCE_UNIT
        ),
        handler_name="HandleSplitClaimBuilderSourceUnitCommandHandler",
    ),
    KnowledgeExtractionImplementedCommandHandler(
        command_type=(
            KnowledgeExtractionCanonicalCommandType.EXECUTE_CLAIM_BUILDER_SECTION
        ),
        handler_name="HandleExecuteClaimBuilderSectionCommandHandler",
    ),
    KnowledgeExtractionImplementedCommandHandler(
        command_type=(
            KnowledgeExtractionCanonicalCommandType.RECONCILE_CLAIM_BUILDER_PROGRESS
        ),
        handler_name="HandleReconcileClaimBuilderProgressCommandHandler",
    ),
    KnowledgeExtractionImplementedCommandHandler(
        command_type=(
            KnowledgeExtractionCanonicalCommandType.GENERATE_DRAFT_CLAIM_EMBEDDINGS
        ),
        handler_name="HandleGenerateDraftClaimEmbeddingsCommandHandler",
    ),
    KnowledgeExtractionImplementedCommandHandler(
        command_type=KnowledgeExtractionCanonicalCommandType.CLUSTER_DRAFT_CLAIMS,
        handler_name="HandleClusterDraftClaimsCommandHandler",
    ),
    KnowledgeExtractionImplementedCommandHandler(
        command_type=(
            KnowledgeExtractionCanonicalCommandType.PREPARE_DRAFT_CLAIM_COMPACTION_DISPATCH_BATCH
        ),
        handler_name="HandlePrepareDraftClaimCompactionDispatchBatchCommandHandler",
    ),
    KnowledgeExtractionImplementedCommandHandler(
        command_type=(
            KnowledgeExtractionCanonicalCommandType.EXECUTE_DRAFT_CLAIM_COMPACTION
        ),
        handler_name="HandleExecuteDraftClaimCompactionCommandHandler",
    ),
    KnowledgeExtractionImplementedCommandHandler(
        command_type=(
            KnowledgeExtractionCanonicalCommandType.APPLY_DRAFT_CLAIM_COMPACTION_RESULT
        ),
        handler_name="HandleApplyDraftClaimCompactionResultCommandHandler",
    ),
    KnowledgeExtractionImplementedCommandHandler(
        command_type=(
            KnowledgeExtractionCanonicalCommandType.RECONCILE_DRAFT_CLAIM_COMPACTION_PROGRESS
        ),
        handler_name="HandleReconcileDraftClaimCompactionProgressCommandHandler",
    ),
    KnowledgeExtractionImplementedCommandHandler(
        command_type=(
            KnowledgeExtractionCanonicalCommandType.OPEN_DRAFT_CLAIM_CURATION_WORKSPACE
        ),
        handler_name="HandleOpenDraftClaimCurationWorkspaceCommandHandler",
    ),
    KnowledgeExtractionImplementedCommandHandler(
        command_type=(
            KnowledgeExtractionCanonicalCommandType.PUBLISH_DRAFT_CLAIM_CURATION_WORKSPACE
        ),
        handler_name="HandlePublishDraftClaimCurationWorkspaceCommandHandler",
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
