from __future__ import annotations

import asyncio
from dataclasses import dataclass

from src.contexts.knowledge_workbench.rag_eval.application.errors.workbench_rag_eval_question_generation_errors import (
    WorkbenchRagEvalDegradedFallbackRequiredError,
    WorkbenchRagEvalQuestionGenerationError,
)
from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval import (
    GeneratedWorkbenchRagEvalQuestion,
)
from src.contexts.knowledge_workbench.rag_eval.application.policies.workbench_rag_eval_question_generation_route_policy import (
    WorkbenchRagEvalQuestionGenerationRoutePolicy,
)
from src.contexts.knowledge_workbench.rag_eval.application.ports.workbench_rag_eval_question_generator_port import (
    WorkbenchRagEvalQuestionGeneratorPort,
)
from src.contexts.knowledge_workbench.retrieval.application.models.published_workbench_retrieval import (
    PublishedWorkbenchRetrievalResult,
)


@dataclass(frozen=True, slots=True)
class WorkbenchRagEvalGeneratedEntryQuestions:
    entry: PublishedWorkbenchRetrievalResult
    generated_questions: tuple[GeneratedWorkbenchRagEvalQuestion, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.entry, PublishedWorkbenchRetrievalResult):
            raise TypeError("entry must be PublishedWorkbenchRetrievalResult")
        if not isinstance(self.generated_questions, tuple):
            raise TypeError("generated_questions must be tuple")


@dataclass(frozen=True, slots=True)
class WorkbenchRagEvalQuestionGenerationBatchExecutor:
    question_generator: WorkbenchRagEvalQuestionGeneratorPort
    route_policy: WorkbenchRagEvalQuestionGenerationRoutePolicy
    max_parallel_jobs: int

    def __post_init__(self) -> None:
        if not isinstance(
            self.route_policy, WorkbenchRagEvalQuestionGenerationRoutePolicy
        ):
            raise TypeError(
                "route_policy must be WorkbenchRagEvalQuestionGenerationRoutePolicy"
            )
        if isinstance(self.max_parallel_jobs, bool) or not isinstance(
            self.max_parallel_jobs, int
        ):
            raise TypeError("max_parallel_jobs must be int")
        if self.max_parallel_jobs < 1:
            raise ValueError("max_parallel_jobs must be positive")

    async def generate_for_entries(
        self,
        *,
        entries: tuple[PublishedWorkbenchRetrievalResult, ...],
        allow_degraded_llama_instant: bool,
    ) -> tuple[WorkbenchRagEvalGeneratedEntryQuestions, ...]:
        if not isinstance(allow_degraded_llama_instant, bool):
            raise TypeError("allow_degraded_llama_instant must be bool")

        semaphore = asyncio.Semaphore(self.max_parallel_jobs)

        async def generate_one(
            entry_index: int,
            entry: PublishedWorkbenchRetrievalResult,
        ) -> WorkbenchRagEvalGeneratedEntryQuestions:
            async with semaphore:
                return await self._generate_one(
                    entry_index=entry_index,
                    entry=entry,
                    allow_degraded_llama_instant=allow_degraded_llama_instant,
                )

        return tuple(
            await asyncio.gather(
                *(generate_one(index, entry) for index, entry in enumerate(entries))
            )
        )

    async def _generate_one(
        self,
        *,
        entry_index: int,
        entry: PublishedWorkbenchRetrievalResult,
        allow_degraded_llama_instant: bool,
    ) -> WorkbenchRagEvalGeneratedEntryQuestions:
        errors: list[str] = []
        candidates = self.route_policy.candidate_chain(
            entry_index=entry_index,
            allow_degraded_llama_instant=allow_degraded_llama_instant,
        )

        for candidate in candidates:
            try:
                generated = await self.question_generator.generate_questions_for_entry(
                    claim=entry.claim,
                    possible_questions=entry.possible_questions,
                    exclusion_scope=entry.exclusion_scope,
                    evidence_block=entry.evidence_block,
                    triples=(),
                    route_candidate=candidate,
                )
                return WorkbenchRagEvalGeneratedEntryQuestions(
                    entry=entry,
                    generated_questions=generated,
                )
            except WorkbenchRagEvalQuestionGenerationError as exc:
                errors.append(f"{candidate.model_ref}/{candidate.account_ref}: {exc}")

        if (
            not allow_degraded_llama_instant
            and self.route_policy.requires_degraded_confirmation_after_automatic_chain()
        ):
            raise WorkbenchRagEvalDegradedFallbackRequiredError(
                "Workbench RAG Eval question generation exhausted automatic "
                "model/account chain. Re-run with allow_degraded_llama_instant=true "
                "to use llama-3.1-8b-instant."
            )

        raise WorkbenchRagEvalQuestionGenerationError(
            "Workbench RAG Eval question generation failed for entry "
            f"{entry.runtime_entry_id}: " + " | ".join(errors)
        )
