from __future__ import annotations

from src.contexts.execution_runtime.application.ports.work_item_lease_repository_port import (
    DueWorkItemRecord,
)
from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.knowledge_workbench.rag_eval.application.workflows.plan_workbench_rag_eval_question_generation_work import (
    WorkbenchRagEvalQuestionGenerationWorkPlanner,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.workbench_rag_eval_dispatch_preparation import (
    make_question_generation_dispatch_preparation_builder,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.workbench_rag_eval_work_kinds import (
    WORKBENCH_RAG_EVAL_QUESTION_GENERATION_WORK_KIND,
)
from src.contexts.knowledge_workbench.retrieval.application.models.published_workbench_retrieval import (
    PublishedWorkbenchRetrievalResult,
    PublishedWorkbenchRetrievalSourceRef,
)


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


def test_qgen_planner_creates_one_work_item_per_runtime_entry() -> None:
    entries = (_entry(1), _entry(2), _entry(3))
    provider_messages = {
        entry.runtime_entry_id: (
            {"role": "system", "content": "system"},
            {"role": "user", "content": f"user {entry.runtime_entry_id}"},
        )
        for entry in entries
    }

    plans = WorkbenchRagEvalQuestionGenerationWorkPlanner(
        prompt_version="prompt-v1",
        generation_model_ref="qwen/qwen3-32b",
    ).plan(
        workflow_run_id="run-1",
        project_id="project-1",
        entries=entries,
        provider_messages_by_runtime_entry_id=provider_messages,
    )

    assert len(plans) == len(entries)
    assert {plan.work_kind for plan in plans} == {
        WORKBENCH_RAG_EVAL_QUESTION_GENERATION_WORK_KIND
    }
    assert {plan.payload["runtime_entry_id"] for plan in plans} == {
        "runtime-entry-1",
        "runtime-entry-2",
        "runtime-entry-3",
    }
    assert all(plan.payload["expected_question_count"] == 10 for plan in plans)
    assert all("llm_capacity_estimate" in plan.payload for plan in plans)


def test_qgen_dispatch_preparation_builder_uses_due_item_estimates() -> None:
    plans = WorkbenchRagEvalQuestionGenerationWorkPlanner(
        prompt_version="prompt-v1",
        generation_model_ref="qwen/qwen3-32b",
    ).plan(
        workflow_run_id="run-1",
        project_id="project-1",
        entries=(_entry(1),),
        provider_messages_by_runtime_entry_id={
            "runtime-entry-1": (
                {"role": "system", "content": "system"},
                {"role": "user", "content": "user"},
            )
        },
    )
    record = DueWorkItemRecord(
        work_item=WorkItem(
            work_item_id=plans[0].work_item_id,
            work_kind=plans[0].work_kind,
        ),
        schedule_payload=dict(plans[0].payload),
    )

    profile = make_question_generation_dispatch_preparation_builder().build_profile_from_due_work_items(
        (record,)
    )

    estimate = plans[0].payload["llm_capacity_estimate"]
    assert isinstance(estimate, dict)
    assert profile.profile_id == "workbench_rag_eval.question_generation.real_due_batch"
    assert profile.estimated_requests == 1
    assert profile.estimated_prompt_tokens == estimate["input_tokens"]
    assert profile.required_window_tokens == estimate["required_window_tokens"]
