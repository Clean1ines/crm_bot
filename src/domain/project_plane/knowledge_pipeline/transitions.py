from collections.abc import Mapping

from .commands import KnowledgePipelineCommand
from .states import KnowledgePipelineState

TransitionTable = Mapping[KnowledgePipelineState, tuple[KnowledgePipelineCommand, ...]]

STATE_ALLOWED_COMMANDS: TransitionTable = {
    KnowledgePipelineState.COMPILER_PARTIAL_FAILED: (
        KnowledgePipelineCommand.RETRY_FAILED_COMPILER_BATCHES,
        KnowledgePipelineCommand.PUBLISH_RAW_DRAFTS_WITHOUT_RESOLUTION,
        KnowledgePipelineCommand.OPEN_DRAFT_REVIEW,
    ),
    KnowledgePipelineState.COMPILER_COMPLETED: (
        KnowledgePipelineCommand.RESUME_KNOWLEDGE_COMPILATION,
        KnowledgePipelineCommand.PUBLISH_RAW_DRAFTS_WITHOUT_RESOLUTION,
        KnowledgePipelineCommand.OPEN_DRAFT_REVIEW,
    ),
    KnowledgePipelineState.ANSWER_RESOLUTION_PENDING: (
        KnowledgePipelineCommand.RESUME_KNOWLEDGE_COMPILATION,
        KnowledgePipelineCommand.PUBLISH_RAW_DRAFTS_WITHOUT_RESOLUTION,
        KnowledgePipelineCommand.OPEN_DRAFT_REVIEW,
    ),
    KnowledgePipelineState.ANSWER_RESOLUTION_RUNNING: (
        KnowledgePipelineCommand.CANCEL_PROCESSING,
        KnowledgePipelineCommand.OPEN_DRAFT_REVIEW,
    ),
    KnowledgePipelineState.PROCESSED: (
        KnowledgePipelineCommand.OPEN_CURATION_CONSOLE,
        KnowledgePipelineCommand.RETIGHTEN_PUBLISHED_ENTRIES,
        KnowledgePipelineCommand.RUN_RETRIEVAL_REVIEW,
    ),
    KnowledgePipelineState.PROCESSED_WITH_WARNINGS: (
        KnowledgePipelineCommand.OPEN_CURATION_CONSOLE,
        KnowledgePipelineCommand.RETIGHTEN_PUBLISHED_ENTRIES,
        KnowledgePipelineCommand.RUN_RETRIEVAL_REVIEW,
    ),
    KnowledgePipelineState.PARTIAL_PUBLISHED: (
        KnowledgePipelineCommand.OPEN_CURATION_CONSOLE,
        KnowledgePipelineCommand.RETIGHTEN_PUBLISHED_ENTRIES,
        KnowledgePipelineCommand.RUN_RETRIEVAL_REVIEW,
    ),
    KnowledgePipelineState.EMBEDDING_FAILED_RETRYABLE: (
        KnowledgePipelineCommand.RESUME_KNOWLEDGE_COMPILATION,
        KnowledgePipelineCommand.OPEN_CURATION_CONSOLE,
    ),
    KnowledgePipelineState.FAILED_FATAL: (KnowledgePipelineCommand.OPEN_DRAFT_REVIEW,),
}
