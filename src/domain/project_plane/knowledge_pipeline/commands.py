from enum import StrEnum


class KnowledgePipelineCommand(StrEnum):
    RETRY_FAILED_COMPILER_BATCHES = "retry_failed_compiler_batches"
    RESUME_KNOWLEDGE_COMPILATION = "resume_knowledge_compilation"
    PUBLISH_RAW_DRAFTS_WITHOUT_RESOLUTION = "publish_raw_drafts_without_resolution"
    CANCEL_PROCESSING = "cancel_processing"
    RETIGHTEN_PUBLISHED_ENTRIES = "retighten_published_entries"
    OPEN_DRAFT_REVIEW = "open_draft_review"
    OPEN_CURATION_CONSOLE = "open_curation_console"
    RUN_RETRIEVAL_REVIEW = "run_retrieval_review"
