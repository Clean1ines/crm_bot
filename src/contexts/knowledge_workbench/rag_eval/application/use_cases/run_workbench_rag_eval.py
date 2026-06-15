from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256

from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval import (
    GeneratedWorkbenchRagEvalQuestion,
    WorkbenchRagEvalPromotedQuestion,
    WorkbenchRagEvalPromotionStatus,
    WorkbenchRagEvalQuestion,
    WorkbenchRagEvalQuestionKind,
    WorkbenchRagEvalQuestionSource,
    WorkbenchRagEvalQuestionStatus,
    WorkbenchRagEvalRetrievalResult,
    WorkbenchRagEvalRun,
    WorkbenchRagEvalRunStatus,
    WorkbenchRagEvalSummary,
)
from src.contexts.knowledge_workbench.rag_eval.application.ports.workbench_rag_eval_question_generator_port import (
    WorkbenchRagEvalQuestionGeneratorPort,
)
from src.contexts.knowledge_workbench.rag_eval.application.ports.workbench_rag_eval_repository_port import (
    WorkbenchRagEvalRepositoryPort,
)
from src.contexts.knowledge_workbench.retrieval.application.models.published_workbench_retrieval import (
    PublishedWorkbenchRetrievalResult,
)
from src.contexts.knowledge_workbench.retrieval.application.use_cases.search_published_workbench_runtime import (
    SearchPublishedWorkbenchRuntime,
)


@dataclass(frozen=True, slots=True)
class RunWorkbenchRagEval:
    rag_eval_repository: WorkbenchRagEvalRepositoryPort
    question_generator: WorkbenchRagEvalQuestionGeneratorPort
    search_published_workbench_runtime: SearchPublishedWorkbenchRuntime
    question_generation_prompt_version: str
    question_generation_model: str | None = None
    default_top_k: int = 5

    async def execute(
        self,
        *,
        project_id: str,
        publication_id: str | None,
        source_document_ref: str | None,
        top_k: int | None,
        max_entries: int,
        now: datetime,
    ) -> WorkbenchRagEvalSummary:
        project_id = _require_text(project_id, "project_id")
        publication_id = _optional_text(publication_id)
        source_document_ref = _optional_text(source_document_ref)
        limit = top_k if top_k is not None else self.default_top_k
        if limit < 5:
            raise ValueError("top_k must be at least 5")
        if max_entries < 1:
            raise ValueError("max_entries must be positive")
        if not self.question_generation_prompt_version.strip():
            raise ValueError("question_generation_prompt_version must be non-empty")

        run_id = _id("workbench-rag-eval-run", project_id, str(now.timestamp()))
        run = WorkbenchRagEvalRun(
            run_id=run_id,
            project_id=project_id,
            publication_id=publication_id,
            source_document_ref=source_document_ref,
            status=WorkbenchRagEvalRunStatus.RUNNING,
            question_generation_model=self.question_generation_model,
            question_generation_prompt_version=self.question_generation_prompt_version,
            total_entries=0,
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
        )
        await self.rag_eval_repository.create_run(run=run)

        entries = await self.rag_eval_repository.list_published_entries_for_eval(
            project_id=project_id,
            publication_id=publication_id,
            source_document_ref=source_document_ref,
            limit=max_entries,
        )

        questions = await self._create_questions(
            run_id=run_id,
            project_id=project_id,
            entries=entries,
            now=now,
        )
        saved_questions = await self.rag_eval_repository.save_generated_questions(
            questions=questions
        )

        retrieval_results, promotions = await self._evaluate_questions(
            run_id=run_id,
            project_id=project_id,
            questions=saved_questions,
            top_k=limit,
            now=now,
        )

        await self.rag_eval_repository.save_retrieval_results(results=retrieval_results)
        await self.rag_eval_repository.save_promoted_question_candidates(
            promotions=promotions
        )

        summary = _summary(
            run_id=run_id,
            project_id=project_id,
            publication_id=publication_id,
            source_document_ref=source_document_ref,
            entries=entries,
            questions=saved_questions,
            retrieval_results=retrieval_results,
            promotion_count=len(promotions),
            created_at=now,
            completed_at=now,
        )
        return await self.rag_eval_repository.complete_run(summary=summary)

    async def _create_questions(
        self,
        *,
        run_id: str,
        project_id: str,
        entries: tuple[PublishedWorkbenchRetrievalResult, ...],
        now: datetime,
    ) -> tuple[WorkbenchRagEvalQuestion, ...]:
        result: list[WorkbenchRagEvalQuestion] = []
        seen_by_entry: dict[str, set[str]] = {}

        for entry in entries:
            generated = await self.question_generator.generate_questions_for_entry(
                claim=entry.claim,
                possible_questions=entry.possible_questions,
                exclusion_scope=entry.exclusion_scope,
                evidence_block=entry.evidence_block,
                triples=(),
            )
            baseline = tuple(
                GeneratedWorkbenchRagEvalQuestion(
                    question=question,
                    question_kind=WorkbenchRagEvalQuestionKind.EXISTING_POSSIBLE_QUESTION,
                    source=WorkbenchRagEvalQuestionSource.PUBLISHED_POSSIBLE_QUESTION,
                    generation_model=None,
                    prompt_version=None,
                )
                for question in entry.possible_questions
            )
            for item in baseline + generated:
                normalized = _normalize_question(item.question)
                entry_seen = seen_by_entry.setdefault(entry.runtime_entry_id, set())
                if normalized in entry_seen:
                    continue
                entry_seen.add(normalized)
                result.append(
                    WorkbenchRagEvalQuestion(
                        question_id=_id(run_id, entry.runtime_entry_id, normalized),
                        run_id=run_id,
                        project_id=project_id,
                        expected_runtime_entry_id=entry.runtime_entry_id,
                        expected_fact_id=entry.fact_id,
                        question=item.question.strip(),
                        question_kind=item.question_kind,
                        source=item.source,
                        generation_model=item.generation_model,
                        prompt_version=item.prompt_version,
                        status=WorkbenchRagEvalQuestionStatus.CREATED,
                        created_at=now,
                    )
                )

        return tuple(result)

    async def _evaluate_questions(
        self,
        *,
        run_id: str,
        project_id: str,
        questions: tuple[WorkbenchRagEvalQuestion, ...],
        top_k: int,
        now: datetime,
    ) -> tuple[
        tuple[WorkbenchRagEvalRetrievalResult, ...],
        tuple[WorkbenchRagEvalPromotedQuestion, ...],
    ]:
        retrieval_results: list[WorkbenchRagEvalRetrievalResult] = []
        promotions: list[WorkbenchRagEvalPromotedQuestion] = []

        for question in questions:
            retrieved = await self.search_published_workbench_runtime.execute(
                project_id=project_id,
                query_text=question.question,
                limit=top_k,
            )
            expected_rank = _expected_rank(
                expected_runtime_entry_id=question.expected_runtime_entry_id,
                retrieved=retrieved,
            )
            top1_hit = expected_rank == 1
            top3_hit = expected_rank is not None and expected_rank <= 3
            top5_hit = expected_rank is not None and expected_rank <= 5

            retrieval_results.extend(
                WorkbenchRagEvalRetrievalResult(
                    result_id=_id(run_id, question.question_id, item.runtime_entry_id),
                    run_id=run_id,
                    question_id=question.question_id,
                    project_id=project_id,
                    expected_runtime_entry_id=question.expected_runtime_entry_id,
                    matched_runtime_entry_id=item.runtime_entry_id,
                    matched_fact_id=item.fact_id,
                    rank=item.rank,
                    score=item.score,
                    top1_hit=top1_hit,
                    top3_hit=top3_hit,
                    top5_hit=top5_hit,
                    created_at=now,
                )
                for item in retrieved
            )

            if not top3_hit:
                promotions.append(
                    WorkbenchRagEvalPromotedQuestion(
                        promotion_id=_id(
                            "workbench-rag-eval-promotion",
                            question.question_id,
                        ),
                        run_id=run_id,
                        question_id=question.question_id,
                        project_id=project_id,
                        target_runtime_entry_id=question.expected_runtime_entry_id,
                        target_fact_id=question.expected_fact_id,
                        question=question.question,
                        status=WorkbenchRagEvalPromotionStatus.CANDIDATE,
                        created_at=now,
                        applied_at=None,
                    )
                )

        return tuple(retrieval_results), tuple(promotions)


def _summary(
    *,
    run_id: str,
    project_id: str,
    publication_id: str | None,
    source_document_ref: str | None,
    entries: tuple[PublishedWorkbenchRetrievalResult, ...],
    questions: tuple[WorkbenchRagEvalQuestion, ...],
    retrieval_results: tuple[WorkbenchRagEvalRetrievalResult, ...],
    promotion_count: int,
    created_at: datetime,
    completed_at: datetime,
) -> WorkbenchRagEvalSummary:
    question_ids = {question.question_id for question in questions}
    top1_hits = {
        result.question_id
        for result in retrieval_results
        if result.top1_hit and result.question_id in question_ids
    }
    top3_hits = {
        result.question_id
        for result in retrieval_results
        if result.top3_hit and result.question_id in question_ids
    }
    top5_hits = {
        result.question_id
        for result in retrieval_results
        if result.top5_hit and result.question_id in question_ids
    }
    misses = len(questions) - len(top5_hits)
    return WorkbenchRagEvalSummary(
        run_id=run_id,
        project_id=project_id,
        publication_id=publication_id,
        source_document_ref=source_document_ref,
        status=WorkbenchRagEvalRunStatus.COMPLETED,
        total_entries=len(entries),
        total_questions=len(questions),
        completed_questions=len(questions),
        top1_hits=len(top1_hits),
        top3_hits=len(top3_hits),
        top5_hits=len(top5_hits),
        misses=misses,
        promotion_candidate_count=promotion_count,
        created_at=created_at,
        completed_at=completed_at,
        error_message=None,
    )


def _expected_rank(
    *,
    expected_runtime_entry_id: str,
    retrieved: tuple[PublishedWorkbenchRetrievalResult, ...],
) -> int | None:
    for item in retrieved:
        if item.runtime_entry_id == expected_runtime_entry_id:
            return item.rank
    return None


def _id(*parts: str) -> str:
    return sha256(":".join(parts).encode("utf-8")).hexdigest()


def _normalize_question(value: str) -> str:
    return " ".join(value.casefold().split())


def _require_text(value: str, field_name: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{field_name} must be non-empty")
    return stripped


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None
