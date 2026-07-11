from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval import (
    WorkbenchRagEvalQuestionAmbiguityRisk,
    WorkbenchRagEvalQuestionDetails,
    WorkbenchRagEvalQuestionKind,
    WorkbenchRagEvalQuestionRole,
    WorkbenchRagEvalQuestionSource,
    WorkbenchRagEvalQuestionStatus,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.handle_run_workbench_rag_eval_retrieval_evaluation_command import (
    HandleRunWorkbenchRagEvalRetrievalEvaluationCommand,
    HandleRunWorkbenchRagEvalRetrievalEvaluationCommandHandler,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.workbench_rag_eval_workflow_definition import (
    WorkbenchRagEvalWorkflowCommandType,
)
from src.contexts.knowledge_workbench.retrieval.application.models.published_workbench_retrieval import (
    PublishedWorkbenchRetrievalResult,
    PublishedWorkbenchRetrievalSourceRef,
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


NOW = datetime(2026, 7, 11, 12, tzinfo=timezone.utc)
PROJECT_ID = "11111111-1111-1111-1111-111111111111"


def _command() -> WorkflowCommand:
    return WorkflowCommand(
        command_id=WorkflowCommandId("workflow-command:retrieval:run-1"),
        command_type=WorkbenchRagEvalWorkflowCommandType.RUN_RETRIEVAL_EVALUATION.value,
        workflow_run_id="run-1",
        idempotency_key=WorkflowIdempotencyKey("retrieval:run-1"),
        payload={
            "workflow_run_id": "run-1",
            "rag_eval_run_id": "run-1",
            "project_id": PROJECT_ID,
            "top_k": 5,
        },
        status=WorkflowCommandStatus.PENDING,
        run_after=NOW,
        created_at=NOW,
        updated_at=NOW,
    )


def _question(
    question_id: str, role: WorkbenchRagEvalQuestionRole
) -> WorkbenchRagEvalQuestionDetails:
    return WorkbenchRagEvalQuestionDetails(
        question_id=question_id,
        run_id="run-1",
        project_id=PROJECT_ID,
        expected_runtime_entry_id="entry-expected",
        expected_fact_id="fact-expected",
        question=f"Как спросить {question_id}?",
        question_kind=WorkbenchRagEvalQuestionKind.ACTION_FIRST
        if role is not WorkbenchRagEvalQuestionRole.BASELINE
        else WorkbenchRagEvalQuestionKind.EXISTING_POSSIBLE_QUESTION,
        source=WorkbenchRagEvalQuestionSource.GENERATED
        if role is not WorkbenchRagEvalQuestionRole.BASELINE
        else WorkbenchRagEvalQuestionSource.PUBLISHED_POSSIBLE_QUESTION,
        generation_model=None
        if role is WorkbenchRagEvalQuestionRole.BASELINE
        else "qwen/qwen3-32b",
        prompt_version=None
        if role is WorkbenchRagEvalQuestionRole.BASELINE
        else "workbench_rag_eval_question_variants.ru.v2",
        contract_version=None
        if role is WorkbenchRagEvalQuestionRole.BASELINE
        else "workbench_rag_eval_questions.v2",
        promotion_eligible=role is WorkbenchRagEvalQuestionRole.PROMOTION_POOL,
        ambiguity_risk=None
        if role is WorkbenchRagEvalQuestionRole.BASELINE
        else WorkbenchRagEvalQuestionAmbiguityRisk.LOW,
        generation_rationale=None
        if role is WorkbenchRagEvalQuestionRole.BASELINE
        else "Alias",
        generation_account_ref=None
        if role is WorkbenchRagEvalQuestionRole.BASELINE
        else "groq_org_primary",
        generation_slot_index=None
        if role is WorkbenchRagEvalQuestionRole.BASELINE
        else 0,
        evaluation_role=role,
        status=WorkbenchRagEvalQuestionStatus.CREATED,
        created_at=NOW,
        results=(),
    )


def _retrieved(
    runtime_entry_id: str, rank: int, score: float
) -> PublishedWorkbenchRetrievalResult:
    return PublishedWorkbenchRetrievalResult(
        runtime_entry_id=runtime_entry_id,
        publication_id="publication-1",
        project_id=PROJECT_ID,
        source_document_ref=None,
        fact_id=f"fact-{runtime_entry_id}",
        curation_item_ref=None,
        claim="Claim",
        possible_questions=("Question?",),
        exclusion_scope=None,
        evidence_block=None,
        source_claim_refs=("claim-1",),
        embedding_text="Claim",
        score=score,
        rank=rank,
        source_ref=PublishedWorkbenchRetrievalSourceRef(
            workflow_run_id=None,
            source_document_ref=None,
            curation_item_ref=None,
            source_claim_refs=("claim-1",),
        ),
    )


@dataclass(slots=True)
class FakeRetrievalSearch:
    calls: list[str] = field(default_factory=list)

    async def execute(self, *, project_id: str, query_text: str, limit: int = 10):
        assert project_id == PROJECT_ID
        assert limit == 5
        self.calls.append(query_text)
        return (
            _retrieved("entry-expected", 1, 0.9),
            _retrieved("entry-other", 2, 0.2),
        )


@dataclass(slots=True)
class FakeRagEvalRepository:
    fail_on_save_results: bool = False
    operations: list[str] = field(default_factory=list)
    questions: tuple[WorkbenchRagEvalQuestionDetails, ...] = (
        _question("q-generated", WorkbenchRagEvalQuestionRole.PROMOTION_POOL),
        _question("q-baseline", WorkbenchRagEvalQuestionRole.BASELINE),
    )

    async def materialize_baseline_questions(self, **kwargs) -> int:
        self.operations.append("baseline")
        return 1

    async def list_run_questions(self, **kwargs):
        self.operations.append("list_questions")
        return self.questions

    async def save_retrieval_results(self, *, results):
        self.operations.append(f"results:{len(results)}")
        if self.fail_on_save_results:
            raise RuntimeError("save failed")
        return results

    async def save_retrieval_outcomes(self, *, outcomes):
        self.operations.append(f"outcomes:{len(outcomes)}")
        return outcomes

    async def mark_questions_evaluated(self, **kwargs) -> None:
        self.operations.append("evaluated")

    async def complete_initial_retrieval_evaluation(self, **kwargs) -> None:
        self.operations.append("counters_phase")


@dataclass(slots=True)
class FakeCommandLog:
    appended: list[WorkflowCommand] = field(default_factory=list)
    completed: list[WorkflowCommandId] = field(default_factory=list)

    async def append_pending_command(self, command: WorkflowCommand):
        if all(existing.command_id != command.command_id for existing in self.appended):
            self.appended.append(command)
        return command

    async def mark_command_completed(self, *, command_id, completed_at):
        self.completed.append(command_id)
        return _command()


@dataclass(slots=True)
class FakeOutbox:
    events: list[object] = field(default_factory=list)

    async def append_event(self, event):
        self.events.append(event)
        return event


@dataclass(slots=True)
class FakeTimeline:
    entries: list[object] = field(default_factory=list)

    async def append_entry(self, entry):
        self.entries.append(entry)
        return entry


@dataclass(slots=True)
class FakeSnapshots:
    snapshots: list[object] = field(default_factory=list)

    async def save_snapshot(self, snapshot):
        self.snapshots.append(snapshot)
        return snapshot


@dataclass(slots=True)
class FakeUow:
    command_log: FakeCommandLog = field(default_factory=FakeCommandLog)
    outbox: FakeOutbox = field(default_factory=FakeOutbox)
    timeline: FakeTimeline = field(default_factory=FakeTimeline)
    progress_snapshots: FakeSnapshots = field(default_factory=FakeSnapshots)


@pytest.mark.asyncio
async def test_retrieval_handler_persists_atomic_vertical_before_completing_command() -> (
    None
):
    repo = FakeRagEvalRepository()
    search = FakeRetrievalSearch()
    uow = FakeUow()

    result = await HandleRunWorkbenchRagEvalRetrievalEvaluationCommandHandler().execute(
        HandleRunWorkbenchRagEvalRetrievalEvaluationCommand(_command()),
        search_published_workbench_runtime=search,
        rag_eval_repository=repo,
        workflow_unit_of_work=uow,
    )

    assert search.calls == ["Как спросить q-generated?", "Как спросить q-baseline?"]
    assert repo.operations == [
        "baseline",
        "list_questions",
        "results:4",
        "outcomes:2",
        "evaluated",
        "counters_phase",
    ]
    assert result.evaluated_question_count == 2
    assert len(uow.command_log.appended) == 1
    assert (
        uow.command_log.appended[0].command_type
        == WorkbenchRagEvalWorkflowCommandType.SCHEDULE_ADJUDICATION_WORK.value
    )
    assert len(uow.outbox.events) == 1
    assert len(uow.timeline.entries) == 1
    assert len(uow.progress_snapshots.snapshots) == 1
    assert uow.command_log.completed == [_command().command_id]


@pytest.mark.asyncio
async def test_retrieval_handler_exception_leaves_current_command_uncompleted() -> None:
    repo = FakeRagEvalRepository(fail_on_save_results=True)
    uow = FakeUow()

    with pytest.raises(RuntimeError, match="save failed"):
        await HandleRunWorkbenchRagEvalRetrievalEvaluationCommandHandler().execute(
            HandleRunWorkbenchRagEvalRetrievalEvaluationCommand(_command()),
            search_published_workbench_runtime=FakeRetrievalSearch(),
            rag_eval_repository=repo,
            workflow_unit_of_work=uow,
        )

    assert repo.operations == ["baseline", "list_questions", "results:4"]
    assert uow.command_log.completed == []
    assert uow.command_log.appended == []
