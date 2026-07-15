from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone

from src.contexts.execution_runtime.application.use_cases.ensure_work_items_scheduled import (
    WorkItemSchedulePlan,
    work_item_schedule_payload_hash,
)
from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval import (
    WorkbenchRagEvalRun,
    WorkbenchRagEvalRunStatus,
)
from src.contexts.knowledge_workbench.rag_eval.application.use_cases.start_workbench_rag_eval_v2 import (
    StartWorkbenchRagEvalV2,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.workbench_rag_eval_work_kinds import (
    WORKBENCH_RAG_EVAL_QUESTION_GENERATION_WORK_KIND,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.workbench_rag_eval_workflow_definition import (
    WorkbenchRagEvalWorkflowCommandType,
)
from src.contexts.workflow_runtime.domain.entities.workflow_command import (
    WorkflowCommand,
)
from src.contexts.knowledge_workbench.rag_eval.infrastructure.llm.workbench_rag_eval_question_generator import (
    WorkbenchRagEvalQuestionGenerator,
)
from src.contexts.knowledge_workbench.retrieval.application.models.published_workbench_retrieval import (
    PublishedWorkbenchRetrievalResult,
    PublishedWorkbenchRetrievalSourceRef,
)
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_model_catalog_seed import (
    model_budget_profile_for_ref,
)


@dataclass(slots=True)
class FakeRagEvalRepository:
    entries: tuple[PublishedWorkbenchRetrievalResult, ...]
    runs: list[WorkbenchRagEvalRun] = field(default_factory=list)

    async def create_run(self, *, run: WorkbenchRagEvalRun) -> WorkbenchRagEvalRun:
        self.runs.append(run)
        return run

    async def list_published_entries_for_eval(
        self,
        *,
        project_id: str,
        publication_id: str | None,
        source_document_ref: str | None,
        limit: int,
    ) -> tuple[PublishedWorkbenchRetrievalResult, ...]:
        del project_id, publication_id, source_document_ref
        return self.entries[:limit]


@dataclass(slots=True)
class FakeSchedulingRepository:
    plans: list[WorkItemSchedulePlan] = field(default_factory=list)
    payload_hashes: dict[str, str] = field(default_factory=dict)

    async def get_work_item(self, work_item_id: str) -> WorkItem | None:
        del work_item_id
        return None

    async def get_schedule_payload_hash(self, work_item_id: str) -> str | None:
        return self.payload_hashes.get(work_item_id)

    async def save_scheduled_work_item(
        self,
        *,
        item: WorkItem,
        idempotency_key: str,
        payload_hash: str,
        payload: Mapping[str, object],
    ) -> None:
        assert idempotency_key == item.work_item_id
        assert payload_hash == work_item_schedule_payload_hash(payload)
        self.plans.append(
            WorkItemSchedulePlan(
                work_item_id=item.work_item_id,
                work_kind=item.work_kind,
                idempotency_key=idempotency_key,
                payload=payload,
            )
        )
        self.payload_hashes[item.work_item_id] = payload_hash


@dataclass(slots=True)
class FakeCommandLog:
    commands: list[WorkflowCommand] = field(default_factory=list)

    async def append_pending_command(
        self,
        command: WorkflowCommand,
    ) -> WorkflowCommand:
        self.commands.append(command)
        return command


def _entry(index: int) -> PublishedWorkbenchRetrievalResult:
    return PublishedWorkbenchRetrievalResult(
        runtime_entry_id=f"runtime-entry-{index}",
        publication_id="pub-1",
        project_id="project-1",
        source_document_ref="doc-1",
        fact_id=f"fact-{index}",
        curation_item_ref=None,
        claim=f"Claim {index}",
        possible_questions=(f"Question {index}?",),
        exclusion_scope=None,
        evidence_block=f"Evidence {index}",
        source_claim_refs=(f"claim-{index}",),
        embedding_text=f"Embedding text {index}",
        score=1.0,
        rank=index,
        source_ref=PublishedWorkbenchRetrievalSourceRef(
            workflow_run_id=None,
            source_document_ref="doc-1",
            curation_item_ref=None,
            source_claim_refs=(f"claim-{index}",),
        ),
    )


async def test_start_v2_creates_running_run_and_schedules_one_qgen_item_per_entry() -> (
    None
):
    rag_eval_repository = FakeRagEvalRepository(entries=(_entry(1), _entry(2)))
    scheduling_repository = FakeSchedulingRepository()
    command_log = FakeCommandLog()
    now = datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)

    summary = await StartWorkbenchRagEvalV2(
        rag_eval_repository=rag_eval_repository,
        work_item_scheduling_repository=scheduling_repository,
        workflow_command_log=command_log,
        question_generator=WorkbenchRagEvalQuestionGenerator.from_prompt_file(),
        question_generation_model_profile=model_budget_profile_for_ref(
            "qwen/qwen3-32b"
        ),
    ).execute(
        project_id="project-1",
        publication_id="pub-1",
        source_document_ref=None,
        max_entries=10,
        now=now,
    )

    assert summary.status is WorkbenchRagEvalRunStatus.RUNNING
    assert summary.total_entries == 2
    assert len(rag_eval_repository.runs) == 1
    assert rag_eval_repository.runs[0].status is WorkbenchRagEvalRunStatus.RUNNING
    assert len(scheduling_repository.plans) == 2
    assert {plan.work_kind for plan in scheduling_repository.plans} == {
        WORKBENCH_RAG_EVAL_QUESTION_GENERATION_WORK_KIND
    }
    assert {
        plan.payload["runtime_entry_id"] for plan in scheduling_repository.plans
    } == {"runtime-entry-1", "runtime-entry-2"}
    assert all(
        plan.payload["expected_question_count"] == 10
        for plan in scheduling_repository.plans
    )

    assert len(command_log.commands) == 1
    initial_command = command_log.commands[0]
    assert initial_command.workflow_run_id == summary.run_id
    assert initial_command.command_type == (
        WorkbenchRagEvalWorkflowCommandType.PREPARE_QUESTION_GENERATION_DISPATCH_BATCH.value
    )
    assert initial_command.payload["workflow_family"] == "workbench_rag_eval"
    assert initial_command.payload["project_id"] == "project-1"
    assert initial_command.payload["publication_id"] == "pub-1"
    assert initial_command.payload["source_document_ref"] is None
    assert initial_command.payload["scheduled_work_item_count"] == 2
    assert initial_command.payload["work_kind"] == (
        WORKBENCH_RAG_EVAL_QUESTION_GENERATION_WORK_KIND.value
    )
    assert initial_command.payload["active_model_ref"] == "qwen/qwen3-32b"
