from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256

from src.contexts.execution_runtime.application.ports.work_item_scheduling_repository_port import (
    WorkItemSchedulingRepositoryPort,
)
from src.contexts.execution_runtime.application.use_cases.ensure_work_items_scheduled import (
    EnsureWorkItemsScheduled,
    EnsureWorkItemsScheduledCommand,
)
from src.contexts.workflow_runtime.application.ports.command_log_repository_port import (
    CommandLogRepositoryPort,
)
from src.contexts.workflow_runtime.domain.entities.workflow_command import (
    WorkflowCommand,
    WorkflowCommandStatus,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_command_id import (
    WorkflowCommandId,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_idempotency_key import (
    WorkflowIdempotencyKey,
)
from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval import (
    WorkbenchRagEvalRun,
    WorkbenchRagEvalRunStatus,
    WorkbenchRagEvalCurrentPhase,
    WorkbenchRagEvalRunProgress,
    WorkbenchRagEvalSummary,
)
from src.contexts.knowledge_workbench.rag_eval.application.ports.workbench_rag_eval_repository_port import (
    WorkbenchRagEvalRepositoryPort,
)
from src.contexts.knowledge_workbench.rag_eval.application.use_cases.run_workbench_rag_eval import (
    WorkbenchRagEvalNoPublishedEntriesError,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.plan_workbench_rag_eval_question_generation_work import (
    WorkbenchRagEvalQuestionGenerationWorkPlanner,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.workbench_rag_eval_work_kinds import (
    WORKBENCH_RAG_EVAL_QUESTION_GENERATION_WORK_KIND,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.workbench_rag_eval_workflow_definition import (
    WorkbenchRagEvalWorkflowCommandType,
    WorkbenchRagEvalWorkflowPhase,
)
from src.contexts.knowledge_workbench.rag_eval.infrastructure.llm.workbench_rag_eval_question_generator import (
    WORKBENCH_RAG_EVAL_QUESTION_PROMPT_VERSION,
    WorkbenchRagEvalQuestionGenerator,
)
from src.contexts.llm_runtime.domain.entities.model_profile import ModelProfile


@dataclass(frozen=True, slots=True)
class StartWorkbenchRagEvalV2:
    rag_eval_repository: WorkbenchRagEvalRepositoryPort
    work_item_scheduling_repository: WorkItemSchedulingRepositoryPort
    workflow_command_log: CommandLogRepositoryPort
    question_generator: WorkbenchRagEvalQuestionGenerator
    question_generation_model_profile: ModelProfile
    question_generation_prompt_version: str = WORKBENCH_RAG_EVAL_QUESTION_PROMPT_VERSION

    async def execute(
        self,
        *,
        project_id: str,
        publication_id: str | None,
        source_document_ref: str | None,
        max_entries: int,
        now: datetime,
    ) -> WorkbenchRagEvalSummary:
        project_id = _require_text(project_id, "project_id")
        publication_id = _optional_text(publication_id)
        source_document_ref = _optional_text(source_document_ref)
        if max_entries < 1:
            raise ValueError("max_entries must be positive")

        entries = await self.rag_eval_repository.list_published_entries_for_eval(
            project_id=project_id,
            publication_id=publication_id,
            source_document_ref=source_document_ref,
            limit=max_entries,
        )
        if not entries:
            raise WorkbenchRagEvalNoPublishedEntriesError(
                "В выбранном документе нет активных опубликованных фактов для проверки."
                if source_document_ref
                else "В опубликованной базе знаний нет активных фактов для проверки."
            )

        run_id = _id("workbench-rag-eval-v2-run", project_id, str(now.timestamp()))
        await self.rag_eval_repository.create_run(
            run=WorkbenchRagEvalRun(
                run_id=run_id,
                project_id=project_id,
                publication_id=publication_id,
                source_document_ref=source_document_ref,
                status=WorkbenchRagEvalRunStatus.RUNNING,
                current_phase=(
                    WorkbenchRagEvalCurrentPhase.QUESTION_GENERATION_SCHEDULING
                ),
                question_generation_model=self.question_generator.generation_model,
                question_generation_prompt_version=(
                    self.question_generation_prompt_version
                ),
                total_entries=len(entries),
                total_questions=0,
                completed_questions=0,
                top1_hits=0,
                top3_hits=0,
                top5_hits=0,
                misses=0,
                created_at=now,
                started_at=now,
                completed_at=None,
                error_message=None,
                updated_at=now,
                progress=WorkbenchRagEvalRunProgress(
                    selected_entries=len(entries),
                    scheduled_generation_items=len(entries),
                    waiting=len(entries),
                ),
            )
        )

        provider_messages = {
            entry.runtime_entry_id: self.question_generator.build_provider_messages(
                claim=entry.claim,
                possible_questions=entry.possible_questions,
                exclusion_scope=entry.exclusion_scope,
                evidence_block=entry.evidence_block,
                triples=(),
            )
            for entry in entries
        }
        plans = WorkbenchRagEvalQuestionGenerationWorkPlanner(
            prompt_version=self.question_generation_prompt_version,
            generation_model_profile=self.question_generation_model_profile,
        ).plan(
            workflow_run_id=run_id,
            project_id=project_id,
            entries=entries,
            provider_messages_by_runtime_entry_id=provider_messages,
        )
        schedule = await EnsureWorkItemsScheduled(
            repository=self.work_item_scheduling_repository,
        ).execute(EnsureWorkItemsScheduledCommand(plans=plans))
        if schedule.conflict_count:
            raise RuntimeError("RAG Eval V2 question-generation schedule conflict")

        await self.workflow_command_log.append_pending_command(
            _initial_question_generation_prepare_command(
                run_id=run_id,
                project_id=project_id,
                publication_id=publication_id,
                source_document_ref=source_document_ref,
                scheduled_work_item_count=len(plans),
                active_model_ref=self.question_generator.generation_model,
                prompt_version=self.question_generation_prompt_version,
                occurred_at=now,
            )
        )

        return WorkbenchRagEvalSummary(
            run_id=run_id,
            project_id=project_id,
            publication_id=publication_id,
            source_document_ref=source_document_ref,
            status=WorkbenchRagEvalRunStatus.RUNNING,
            current_phase=(WorkbenchRagEvalCurrentPhase.QUESTION_GENERATION_SCHEDULING),
            total_entries=len(entries),
            total_questions=0,
            completed_questions=0,
            top1_hits=0,
            top3_hits=0,
            top5_hits=0,
            misses=0,
            promotion_candidate_count=0,
            created_at=now,
            completed_at=None,
            error_message=None,
            updated_at=now,
            progress=WorkbenchRagEvalRunProgress(
                selected_entries=len(entries),
                scheduled_generation_items=len(plans),
                waiting=len(plans),
            ),
        )


def _initial_question_generation_prepare_command(
    *,
    run_id: str,
    project_id: str,
    publication_id: str | None,
    source_document_ref: str | None,
    scheduled_work_item_count: int,
    active_model_ref: str,
    prompt_version: str,
    occurred_at: datetime,
) -> WorkflowCommand:
    if scheduled_work_item_count <= 0:
        raise ValueError("scheduled_work_item_count must be positive")

    idempotency_key = f"prepare-rag-eval-question-generation:{run_id}:initial"
    payload: dict[str, object] = {
        "workflow_family": "workbench_rag_eval",
        "workflow_run_id": run_id,
        "rag_eval_run_id": run_id,
        "project_id": project_id,
        "publication_id": publication_id,
        "source_document_ref": source_document_ref,
        "work_kind": (WORKBENCH_RAG_EVAL_QUESTION_GENERATION_WORK_KIND.value),
        "scheduled_work_item_count": scheduled_work_item_count,
        "active_model_ref": active_model_ref,
        "prompt_version": prompt_version,
        "current_phase": (WorkbenchRagEvalWorkflowPhase.QUESTION_GENERATION.value),
        "causation": {
            "kind": "rag_eval_start",
            "run_id": run_id,
        },
    }
    return WorkflowCommand(
        command_id=WorkflowCommandId(f"workflow-command:{idempotency_key}"),
        command_type=(
            WorkbenchRagEvalWorkflowCommandType.PREPARE_QUESTION_GENERATION_DISPATCH_BATCH.value
        ),
        workflow_run_id=run_id,
        idempotency_key=WorkflowIdempotencyKey(idempotency_key),
        payload=payload,
        status=WorkflowCommandStatus.PENDING,
        run_after=occurred_at,
        created_at=occurred_at,
        updated_at=occurred_at,
    )


def _id(*parts: str) -> str:
    return sha256(":".join(parts).encode("utf-8")).hexdigest()


def _require_text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{field_name} must be non-empty")
    return stripped


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None
