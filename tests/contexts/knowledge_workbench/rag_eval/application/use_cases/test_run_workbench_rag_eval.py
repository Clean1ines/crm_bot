from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from collections.abc import Mapping

import pytest

from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval import (
    GeneratedWorkbenchRagEvalQuestion,
    WorkbenchRagEvalPromotedQuestion,
    WorkbenchRagEvalQuestion,
    WorkbenchRagEvalQuestionKind,
    WorkbenchRagEvalQuestionSource,
    WorkbenchRagEvalRetrievalResult,
    WorkbenchRagEvalRun,
    WorkbenchRagEvalSummary,
)
from src.contexts.knowledge_workbench.rag_eval.application.policies.workbench_rag_eval_question_generation_route_policy import (
    WorkbenchRagEvalQuestionGenerationRoutePolicy,
)
from src.contexts.knowledge_workbench.rag_eval.application.use_cases.generate_workbench_rag_eval_questions_batch import (
    WorkbenchRagEvalQuestionGenerationBatchExecutor,
)
from src.contexts.knowledge_workbench.rag_eval.application.use_cases.run_workbench_rag_eval import (
    RunWorkbenchRagEval,
)
from src.contexts.knowledge_workbench.retrieval.application.models.published_workbench_retrieval import (
    PublishedWorkbenchRetrievalResult,
    PublishedWorkbenchRetrievalSourceRef,
)


def _now() -> datetime:
    return datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)


def _entry(
    entry_id: str, *, possible_questions: tuple[str, ...]
) -> PublishedWorkbenchRetrievalResult:
    return PublishedWorkbenchRetrievalResult(
        runtime_entry_id=entry_id,
        publication_id="publication-1",
        project_id="project-1",
        source_document_ref="source-document-1",
        fact_id=f"fact-{entry_id}",
        curation_item_ref=f"item-{entry_id}",
        claim=f"Claim {entry_id}",
        possible_questions=possible_questions,
        exclusion_scope=None,
        evidence_block=None,
        source_claim_refs=("raw-1",),
        embedding_text=f"Claim:\\nClaim {entry_id}",
        score=1.0,
        rank=1,
        source_ref=PublishedWorkbenchRetrievalSourceRef(
            workflow_run_id="workflow-1",
            source_document_ref="source-document-1",
            curation_item_ref=f"item-{entry_id}",
            source_claim_refs=("raw-1",),
        ),
    )


@dataclass(slots=True)
class FakeRepository:
    entries: tuple[PublishedWorkbenchRetrievalResult, ...]
    runs: list[WorkbenchRagEvalRun] = field(default_factory=list)
    questions: tuple[WorkbenchRagEvalQuestion, ...] = ()
    results: tuple[WorkbenchRagEvalRetrievalResult, ...] = ()
    promotions: tuple[WorkbenchRagEvalPromotedQuestion, ...] = ()
    summary: WorkbenchRagEvalSummary | None = None

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
        assert project_id == "project-1"
        assert publication_id == "publication-1"
        assert source_document_ref is None
        return self.entries[:limit]

    async def save_generated_questions(
        self,
        *,
        questions: tuple[WorkbenchRagEvalQuestion, ...],
    ) -> tuple[WorkbenchRagEvalQuestion, ...]:
        self.questions = questions
        return questions

    async def save_retrieval_results(
        self,
        *,
        results: tuple[WorkbenchRagEvalRetrievalResult, ...],
    ) -> tuple[WorkbenchRagEvalRetrievalResult, ...]:
        self.results = results
        return results

    async def save_promoted_question_candidates(
        self,
        *,
        promotions: tuple[WorkbenchRagEvalPromotedQuestion, ...],
    ) -> tuple[WorkbenchRagEvalPromotedQuestion, ...]:
        self.promotions = promotions
        return promotions

    async def complete_run(
        self,
        *,
        summary: WorkbenchRagEvalSummary,
    ) -> WorkbenchRagEvalSummary:
        self.summary = summary
        return summary

    async def get_latest_run(
        self,
        *,
        project_id: str,
    ) -> WorkbenchRagEvalSummary | None:
        return self.summary

    async def get_run(
        self,
        *,
        run_id: str,
        project_id: str,
    ) -> WorkbenchRagEvalSummary | None:
        return self.summary


@dataclass(slots=True)
class FakeQuestionGenerator:
    calls: list[str] = field(default_factory=list)
    account_refs: list[str] = field(default_factory=list)

    async def generate_questions_for_entry(
        self,
        *,
        claim: str,
        possible_questions: tuple[str, ...],
        exclusion_scope: str | None,
        evidence_block: str | None,
        triples: tuple[Mapping[str, object], ...],
        route_candidate,
    ) -> tuple[GeneratedWorkbenchRagEvalQuestion, ...]:
        del possible_questions, exclusion_scope, evidence_block, triples
        self.calls.append(claim)
        self.account_refs.append(route_candidate.account_ref)
        return (
            GeneratedWorkbenchRagEvalQuestion(
                question=f"Generated {claim}?",
                question_kind=WorkbenchRagEvalQuestionKind.PARAPHRASE,
                source=WorkbenchRagEvalQuestionSource.GENERATED,
                generation_model=route_candidate.model_ref,
                prompt_version="test-v1",
                generation_account_ref=route_candidate.account_ref,
                generation_slot_index=route_candidate.slot_index,
            ),
            GeneratedWorkbenchRagEvalQuestion(
                question=f"Generated {claim}?",
                question_kind=WorkbenchRagEvalQuestionKind.SYNONYM,
                source=WorkbenchRagEvalQuestionSource.GENERATED,
                generation_model=route_candidate.model_ref,
                prompt_version="test-v1",
                generation_account_ref=route_candidate.account_ref,
                generation_slot_index=route_candidate.slot_index,
            ),
        )


@dataclass(slots=True)
class FakeSearchPublishedWorkbenchRuntime:
    calls: list[str] = field(default_factory=list)

    async def execute(
        self,
        *,
        project_id: str,
        query_text: str,
        limit: int = 10,
    ) -> tuple[PublishedWorkbenchRetrievalResult, ...]:
        assert project_id == "project-1"
        assert limit == 5
        self.calls.append(query_text)
        if "miss" in query_text.casefold():
            return (_entry("other-entry", possible_questions=("Other?",)),)
        return (_entry("entry-1", possible_questions=("Existing?",)),)


@pytest.mark.asyncio
async def test_run_includes_baseline_generated_dedupes_and_metrics() -> None:
    repository = FakeRepository(
        entries=(_entry("entry-1", possible_questions=("Existing?", "miss me")),)
    )
    generator = FakeQuestionGenerator()
    search = FakeSearchPublishedWorkbenchRuntime()

    summary = await RunWorkbenchRagEval(
        rag_eval_repository=repository,
        question_generation_batch_executor=WorkbenchRagEvalQuestionGenerationBatchExecutor(
            question_generator=generator,
            route_policy=WorkbenchRagEvalQuestionGenerationRoutePolicy.default(),
            max_parallel_jobs=4,
        ),
        search_published_workbench_runtime=search,
        question_generation_prompt_version="test-v1",
        question_generation_model="fake-generator",
    ).execute(
        project_id="project-1",
        publication_id="publication-1",
        source_document_ref=None,
        top_k=5,
        max_entries=20,
        now=_now(),
    )

    assert summary.total_entries == 1
    assert summary.total_questions == 3
    assert summary.completed_questions == 3
    assert summary.top1_hits == 2
    assert summary.top3_hits == 2
    assert summary.top5_hits == 2
    assert summary.misses == 1
    assert summary.promotion_candidate_count == 1
    assert len(repository.promotions) == 1
    assert repository.promotions[0].status.value == "candidate"
    assert search.calls == ["Existing?", "miss me", "Generated Claim entry-1?"]
    assert generator.calls == ["Claim entry-1"]
    assert generator.account_refs == ["groq_org_primary"]
    generated_questions = tuple(
        question
        for question in repository.questions
        if question.source.value == "generated"
    )
    assert generated_questions[0].generation_model == "qwen/qwen3-32b"
    assert generated_questions[0].generation_account_ref == "groq_org_primary"
    assert generated_questions[0].generation_slot_index == 0


@pytest.mark.asyncio
async def test_run_rejects_top_k_below_five() -> None:
    with pytest.raises(ValueError):
        await RunWorkbenchRagEval(
            rag_eval_repository=FakeRepository(entries=()),
            question_generation_batch_executor=WorkbenchRagEvalQuestionGenerationBatchExecutor(
                question_generator=FakeQuestionGenerator(),
                route_policy=WorkbenchRagEvalQuestionGenerationRoutePolicy.default(),
                max_parallel_jobs=4,
            ),
            search_published_workbench_runtime=FakeSearchPublishedWorkbenchRuntime(),
            question_generation_prompt_version="test-v1",
        ).execute(
            project_id="project-1",
            publication_id=None,
            source_document_ref=None,
            top_k=3,
            max_entries=20,
            now=_now(),
        )
