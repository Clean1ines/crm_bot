from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias

CleanupScope: TypeAlias = Literal["document", "project"]

CleanupMode: TypeAlias = Literal[
    "manual_cancel",
    "reset_for_reprocess",
    "delete_document",
    "clear_project",
]

CleanupReason: TypeAlias = Literal[
    "manual_cancel",
    "explicit_user_resume",
    "normal_reprocess",
    "delete_document",
    "clear_project",
    "project_reset",
]

SCOPE_DOCUMENT: CleanupScope = "document"
SCOPE_PROJECT: CleanupScope = "project"

MODE_MANUAL_CANCEL: CleanupMode = "manual_cancel"
MODE_RESET_FOR_REPROCESS: CleanupMode = "reset_for_reprocess"
MODE_DELETE_DOCUMENT: CleanupMode = "delete_document"
MODE_CLEAR_PROJECT: CleanupMode = "clear_project"

REASON_MANUAL_CANCEL: CleanupReason = "manual_cancel"
REASON_EXPLICIT_USER_RESUME: CleanupReason = "explicit_user_resume"
REASON_NORMAL_REPROCESS: CleanupReason = "normal_reprocess"
REASON_DELETE_DOCUMENT: CleanupReason = "delete_document"
REASON_CLEAR_PROJECT: CleanupReason = "clear_project"
REASON_PROJECT_RESET: CleanupReason = "project_reset"

DOCUMENT_METADATA_TABLES: tuple[str, ...] = ("knowledge_documents",)

LEGACY_RUNTIME_TABLES: tuple[str, ...] = ("knowledge_base",)

DOCUMENT_SOURCE_TABLES: tuple[str, ...] = ("knowledge_source_chunks",)

DOCUMENT_ENTRY_TABLES: tuple[str, ...] = (
    "knowledge_entry_source_refs",
    "knowledge_retrieval_surface",
    "knowledge_entries",
    "knowledge_entry_versions",
    "knowledge_edit_actions",
)

DOCUMENT_COMPILER_TABLES: tuple[str, ...] = (
    "knowledge_compiler_batches",
    "knowledge_compilation_metrics",
    "knowledge_candidate_cluster_members",
    "knowledge_candidate_clusters",
    "knowledge_answer_candidates",
    "knowledge_compiler_runs",
)

DOCUMENT_SURFACE_TABLES: tuple[str, ...] = (
    "knowledge_surface_reassignment_decisions",
    "knowledge_surface_ownership_decisions",
    "knowledge_surface_merge_decisions",
    "knowledge_surface_relations",
    "knowledge_surface_cards",
    "knowledge_surface_draft_cards",
    "knowledge_surface_source_units",
    "knowledge_surface_compiler_stages",
    "knowledge_surface_compiler_runs",
)

DOCUMENT_RAG_EVAL_TABLES: tuple[str, ...] = (
    "rag_eval_review_groups",
    "rag_eval_question_reviews",
    "rag_eval_results",
    "rag_eval_run_failures",
    "rag_eval_runs",
    "rag_eval_questions",
    "rag_eval_datasets",
)

DOCUMENT_QUEUE_TABLES: tuple[str, ...] = ("execution_queue",)

DOCUMENT_ARTIFACT_TABLES: tuple[str, ...] = (
    *LEGACY_RUNTIME_TABLES,
    *DOCUMENT_SOURCE_TABLES,
    *DOCUMENT_ENTRY_TABLES,
    *DOCUMENT_COMPILER_TABLES,
    *DOCUMENT_SURFACE_TABLES,
    *DOCUMENT_RAG_EVAL_TABLES,
)

DESTRUCTIVE_DOCUMENT_TABLES: tuple[str, ...] = (
    *DOCUMENT_ARTIFACT_TABLES,
    *DOCUMENT_QUEUE_TABLES,
)

DELETE_DOCUMENT_TABLES: tuple[str, ...] = (
    *DOCUMENT_METADATA_TABLES,
    *DESTRUCTIVE_DOCUMENT_TABLES,
)

PROJECT_CLEAR_TABLES: tuple[str, ...] = (
    *DOCUMENT_METADATA_TABLES,
    *DESTRUCTIVE_DOCUMENT_TABLES,
)


@dataclass(frozen=True)
class KnowledgeArtifactCleanupCounters:
    documents: int = 0
    legacy_runtime_rows: int = 0
    source_chunks: int = 0
    entries: int = 0
    entry_source_refs: int = 0
    retrieval_surface_rows: int = 0
    entry_versions: int = 0
    edit_actions: int = 0
    compiler_runs: int = 0
    compiler_batches: int = 0
    answer_candidates: int = 0
    candidate_clusters: int = 0
    surface_runs: int = 0
    surface_source_units: int = 0
    surface_cards: int = 0
    surface_relations: int = 0
    rag_eval_artifacts: int = 0
    execution_queue_jobs: int = 0

    @property
    def total(self) -> int:
        return (
            self.documents
            + self.legacy_runtime_rows
            + self.source_chunks
            + self.entries
            + self.entry_source_refs
            + self.retrieval_surface_rows
            + self.entry_versions
            + self.edit_actions
            + self.compiler_runs
            + self.compiler_batches
            + self.answer_candidates
            + self.candidate_clusters
            + self.surface_runs
            + self.surface_source_units
            + self.surface_cards
            + self.surface_relations
            + self.rag_eval_artifacts
            + self.execution_queue_jobs
        )


@dataclass(frozen=True)
class KnowledgeArtifactCleanupPlan:
    project_id: str
    scope: CleanupScope
    mode: CleanupMode
    reason: CleanupReason
    document_id: str | None
    destructive: bool
    affected_tables: tuple[str, ...]
    cancel_running_jobs: bool = False
    reset_document_state: bool = False
    delete_document_row: bool = False
    clear_project_documents: bool = False
    cleanup_legacy_runtime: bool = False
    cleanup_source_chunks: bool = False
    cleanup_entries: bool = False
    cleanup_retrieval_surface: bool = False
    cleanup_compiler_artifacts: bool = False
    cleanup_surface_artifacts: bool = False
    cleanup_rag_eval_artifacts: bool = False
    cleanup_edit_history: bool = False
    cleanup_execution_queue: bool = False
    retain_audit_history: bool = True

    def __post_init__(self) -> None:
        if not self.project_id.strip():
            raise ValueError("project_id must be non-empty")

        if self.scope == SCOPE_DOCUMENT and not (self.document_id or "").strip():
            raise ValueError("document cleanup scope requires document_id")

        if self.scope == SCOPE_PROJECT and self.document_id is not None:
            raise ValueError("project cleanup scope must not include document_id")

        if not self.affected_tables:
            raise ValueError("cleanup plan must declare affected_tables")

        if self.mode == MODE_MANUAL_CANCEL and self.destructive:
            raise ValueError("manual cancel must not be destructive cleanup")

        if (
            self.mode
            in {
                MODE_RESET_FOR_REPROCESS,
                MODE_DELETE_DOCUMENT,
                MODE_CLEAR_PROJECT,
            }
            and not self.destructive
        ):
            raise ValueError(f"{self.mode} must be destructive cleanup")


@dataclass(frozen=True)
class KnowledgeArtifactCleanupResult:
    plan: KnowledgeArtifactCleanupPlan
    counters: KnowledgeArtifactCleanupCounters = KnowledgeArtifactCleanupCounters()
    completed: bool = True
    warnings: tuple[str, ...] = ()

    @property
    def destructive(self) -> bool:
        return self.plan.destructive

    @property
    def affected_total(self) -> int:
        return self.counters.total


def build_manual_cancel_cleanup_plan(
    *,
    project_id: str,
    document_id: str,
) -> KnowledgeArtifactCleanupPlan:
    return KnowledgeArtifactCleanupPlan(
        project_id=project_id,
        document_id=document_id,
        scope=SCOPE_DOCUMENT,
        mode=MODE_MANUAL_CANCEL,
        reason=REASON_MANUAL_CANCEL,
        destructive=False,
        affected_tables=(
            *DOCUMENT_METADATA_TABLES,
            *DOCUMENT_QUEUE_TABLES,
        ),
        cancel_running_jobs=True,
        cleanup_execution_queue=True,
        retain_audit_history=True,
    )


def build_document_reset_cleanup_plan(
    *,
    project_id: str,
    document_id: str,
    reason: CleanupReason = REASON_NORMAL_REPROCESS,
) -> KnowledgeArtifactCleanupPlan:
    return KnowledgeArtifactCleanupPlan(
        project_id=project_id,
        document_id=document_id,
        scope=SCOPE_DOCUMENT,
        mode=MODE_RESET_FOR_REPROCESS,
        reason=reason,
        destructive=True,
        affected_tables=DESTRUCTIVE_DOCUMENT_TABLES,
        cancel_running_jobs=True,
        reset_document_state=True,
        cleanup_legacy_runtime=True,
        cleanup_source_chunks=True,
        cleanup_entries=True,
        cleanup_retrieval_surface=True,
        cleanup_compiler_artifacts=True,
        cleanup_surface_artifacts=True,
        cleanup_rag_eval_artifacts=True,
        cleanup_edit_history=True,
        cleanup_execution_queue=True,
        retain_audit_history=False,
    )


def build_document_delete_cleanup_plan(
    *,
    project_id: str,
    document_id: str,
) -> KnowledgeArtifactCleanupPlan:
    return KnowledgeArtifactCleanupPlan(
        project_id=project_id,
        document_id=document_id,
        scope=SCOPE_DOCUMENT,
        mode=MODE_DELETE_DOCUMENT,
        reason=REASON_DELETE_DOCUMENT,
        destructive=True,
        affected_tables=DELETE_DOCUMENT_TABLES,
        cancel_running_jobs=True,
        delete_document_row=True,
        cleanup_legacy_runtime=True,
        cleanup_source_chunks=True,
        cleanup_entries=True,
        cleanup_retrieval_surface=True,
        cleanup_compiler_artifacts=True,
        cleanup_surface_artifacts=True,
        cleanup_rag_eval_artifacts=True,
        cleanup_edit_history=True,
        cleanup_execution_queue=True,
        retain_audit_history=False,
    )


def build_project_clear_cleanup_plan(
    *,
    project_id: str,
    reason: CleanupReason = REASON_CLEAR_PROJECT,
) -> KnowledgeArtifactCleanupPlan:
    return KnowledgeArtifactCleanupPlan(
        project_id=project_id,
        document_id=None,
        scope=SCOPE_PROJECT,
        mode=MODE_CLEAR_PROJECT,
        reason=reason,
        destructive=True,
        affected_tables=PROJECT_CLEAR_TABLES,
        cancel_running_jobs=True,
        clear_project_documents=True,
        cleanup_legacy_runtime=True,
        cleanup_source_chunks=True,
        cleanup_entries=True,
        cleanup_retrieval_surface=True,
        cleanup_compiler_artifacts=True,
        cleanup_surface_artifacts=True,
        cleanup_rag_eval_artifacts=True,
        cleanup_edit_history=True,
        cleanup_execution_queue=True,
        retain_audit_history=False,
    )
