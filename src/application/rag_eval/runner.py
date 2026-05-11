from __future__ import annotations

from time import perf_counter

from src.application.rag_eval.ports import (
    RagEvalAnswerJudgePort,
    RagEvalAnswererPort,
    RagEvalRetrieverPort,
)
from src.application.rag_eval.schemas import (
    RagEvalQuestion,
    RagEvalResult,
    new_eval_id,
)


TECHNICAL_ANSWER_MARKERS = (
    "Не получилось сгенерировать ответ из-за технической ошибки",
    "Техническая ошибка повторилась",
    "Не получилось обработать запрос из-за технической ошибки",
)


class RagEvalTechnicalAnswerError(RuntimeError):
    """Raised when production answer generation returned a technical fallback.

    This is not a RAG quality failure. It means the provider/runtime failed
    before a real answer could be evaluated, so the full-document eval should
    pause/retry instead of polluting the quality report with artificial zeroes.
    """

    def __init__(self, answer_text: str) -> None:
        super().__init__(answer_text[:500])
        self.answer_text = answer_text


def is_rag_eval_technical_answer(answer_text: str) -> bool:
    normalized = " ".join(answer_text.split())
    return any(marker in normalized for marker in TECHNICAL_ANSWER_MARKERS)


class RagEvalRunner:
    def __init__(
        self,
        *,
        retriever: RagEvalRetrieverPort,
        answerer: RagEvalAnswererPort,
        answer_judge: RagEvalAnswerJudgePort,
        retrieval_limit: int = 5,
    ) -> None:
        self._retriever = retriever
        self._answerer = answerer
        self._answer_judge = answer_judge
        self._retrieval_limit = retrieval_limit

    async def run_question(
        self,
        *,
        run_id: str,
        project_id: str,
        question: RagEvalQuestion,
    ) -> RagEvalResult:
        started = perf_counter()

        retrieved_chunks = await self._retriever.retrieve(
            project_id=project_id,
            question=question.question,
            limit=self._retrieval_limit,
        )

        answer_text = await self._answerer.answer(
            project_id=project_id,
            question=question.question,
            evidence=retrieved_chunks,
        )

        if is_rag_eval_technical_answer(answer_text):
            raise RagEvalTechnicalAnswerError(answer_text)

        judge = await self._answer_judge.judge_answer(
            question=question,
            retrieved_chunks=retrieved_chunks,
            answer_text=answer_text,
        )

        latency_ms = int((perf_counter() - started) * 1000)
        retrieved_ids = [chunk.id for chunk in retrieved_chunks]
        expected_ids = set(question.expected_chunk_ids)

        top1_hit = bool(expected_ids and expected_ids.intersection(retrieved_ids[:1]))
        top3_hit = bool(expected_ids and expected_ids.intersection(retrieved_ids[:3]))
        top5_hit = bool(expected_ids and expected_ids.intersection(retrieved_ids[:5]))
        expected_chunk_found = bool(
            expected_ids and expected_ids.intersection(retrieved_ids)
        )
        wrong_chunk_top1 = bool(
            expected_ids and retrieved_ids and retrieved_ids[0] not in expected_ids
        )

        deterministic_score = self._deterministic_score(
            question=question,
            top1_hit=top1_hit,
            top3_hit=top3_hit,
            top5_hit=top5_hit,
            expected_chunk_found=expected_chunk_found,
            wrong_chunk_top1=wrong_chunk_top1,
        )
        final_score = self._final_score(
            question=question,
            deterministic_score=deterministic_score,
            judge_score=judge.score,
            should_answer_passed=judge.should_answer_passed,
            answer_supported=judge.answer_supported,
            hallucination_risk=judge.hallucination_risk,
        )

        return RagEvalResult(
            id=new_eval_id("result"),
            run_id=run_id,
            question_id=question.id,
            question=question,
            retrieved_chunks=retrieved_chunks,
            answer_text=answer_text,
            top1_hit=top1_hit,
            top3_hit=top3_hit,
            top5_hit=top5_hit,
            expected_chunk_found=expected_chunk_found,
            wrong_chunk_top1=wrong_chunk_top1,
            answer_supported=judge.answer_supported,
            hallucination_risk=judge.hallucination_risk,
            should_answer_passed=judge.should_answer_passed,
            score=final_score,
            notes=judge.notes,
            latency_ms=latency_ms,
            judge_json=judge.to_json(),
        )

    def failed_result(
        self,
        *,
        run_id: str,
        question: RagEvalQuestion,
        error: BaseException,
        stage: str = "question_execution",
    ) -> RagEvalResult:
        error_type = type(error).__name__
        error_message = str(error).strip()[:700]
        notes = f"{stage} failed with {error_type}: {error_message}"

        return RagEvalResult(
            id=new_eval_id("result"),
            run_id=run_id,
            question_id=question.id,
            question=question,
            retrieved_chunks=[],
            answer_text="",
            top1_hit=False,
            top3_hit=False,
            top5_hit=False,
            expected_chunk_found=False,
            wrong_chunk_top1=bool(question.expected_chunk_ids),
            answer_supported=False,
            hallucination_risk="high",
            should_answer_passed=not question.should_answer,
            score=0.0,
            notes=notes[:1000],
            latency_ms=0,
            judge_json={
                "error": error_message,
                "error_type": error_type,
                "stage": stage,
                "recovered": True,
            },
        )

    def _deterministic_score(
        self,
        *,
        question: RagEvalQuestion,
        top1_hit: bool,
        top3_hit: bool,
        top5_hit: bool,
        expected_chunk_found: bool,
        wrong_chunk_top1: bool,
    ) -> float:
        if not question.expected_chunk_ids:
            return 1.0 if not wrong_chunk_top1 else 0.35

        if top1_hit:
            return 1.0
        if top3_hit:
            return 0.82
        if top5_hit:
            return 0.68
        if expected_chunk_found:
            return 0.55
        if wrong_chunk_top1:
            return 0.15
        return 0.25

    def _final_score(
        self,
        *,
        question: RagEvalQuestion,
        deterministic_score: float,
        judge_score: float,
        should_answer_passed: bool,
        answer_supported: bool,
        hallucination_risk: str,
    ) -> float:
        """Combine retrieval and answer quality.

        Retrieval correctness is primary for answerable questions.
        For no-answer questions, behavior/generation policy is primary:
        a hallucinated answer must not be rescued by a neutral retrieval score.
        """
        base_score = (deterministic_score * 0.6) + (judge_score * 0.4)

        if not question.should_answer:
            if not should_answer_passed:
                base_score = min(base_score, judge_score)
            if hallucination_risk == "high":
                base_score = min(base_score, 0.25)
            if answer_supported:
                base_score = min(base_score, 0.45)

        if question.should_answer and not answer_supported:
            base_score = min(base_score, 0.45)

        return round(base_score, 4)
