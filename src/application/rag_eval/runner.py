from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from collections.abc import Mapping
from typing import Literal, TypeAlias

from src.application.rag_eval.failure_classification import (
    FailureClassification,
    FailureStage,
    FailureType,
    propose_knowledge_edit_actions,
)
from src.application.rag_eval.ports import (
    RagEvalAnswerJudgePort,
    RagEvalAnswererPort,
    RagEvalRetrieverPort,
)
from src.application.rag_eval.schemas import (
    RagEvalEvidenceEntry,
    RagEvalQuestion,
    JsonObject,
    RagEvalResult,
    json_value,
    new_eval_id,
)


RagEvalMode: TypeAlias = Literal["retrieval_eval", "answer_quality_eval"]

TECHNICAL_ANSWER_MARKERS = (
    "Не получилось сгенерировать ответ из-за технической ошибки",
    "Техническая ошибка повторилась",
    "Не получилось обработать запрос из-за технической ошибки",
)


@dataclass(frozen=True, slots=True)
class _RetrievalEvaluation:
    retrieved_ids: tuple[str, ...]
    expected_ids: frozenset[str]
    top1_hit: bool
    top3_hit: bool
    top5_hit: bool
    expected_entry_found: bool
    wrong_entry_top1: bool
    expected_entry_rank: int | None


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
        answerer: RagEvalAnswererPort | None = None,
        answer_judge: RagEvalAnswerJudgePort | None = None,
        mode: RagEvalMode = "retrieval_eval",
        retrieval_limit: int = 5,
        retrieval_metadata: Mapping[str, object] | None = None,
    ) -> None:
        self._retriever = retriever
        self._answerer = answerer
        self._answer_judge = answer_judge
        self._mode = mode
        self._retrieval_limit = retrieval_limit
        self._retrieval_metadata: JsonObject = {
            str(key): json_value(value)
            for key, value in dict(retrieval_metadata or {}).items()
        }

    def _judge_json(self, payload: Mapping[str, object]) -> JsonObject:
        result = {str(key): json_value(value) for key, value in payload.items()}
        result.update(self._retrieval_metadata)
        return result

    async def run_question(
        self,
        *,
        run_id: str,
        project_id: str,
        question: RagEvalQuestion,
    ) -> RagEvalResult:
        started = perf_counter()

        retrieved_entries = await self._retriever.retrieve(
            project_id=project_id,
            question=question.question,
            limit=self._retrieval_limit,
        )
        retrieval = self._evaluate_retrieval(
            question=question,
            retrieved_ids=tuple(entry.id for entry in retrieved_entries),
        )

        if self._mode == "retrieval_eval":
            latency_ms = int((perf_counter() - started) * 1000)
            return self._retrieval_only_result(
                run_id=run_id,
                question=question,
                retrieved_entries=retrieved_entries,
                retrieval=retrieval,
                latency_ms=latency_ms,
            )

        if self._answerer is None or self._answer_judge is None:
            raise RuntimeError(
                "answer_quality_eval requires both answerer and answer_judge"
            )

        answer_text = await self._answerer.answer(
            project_id=project_id,
            question=question.question,
            evidence=retrieved_entries,
        )

        if is_rag_eval_technical_answer(answer_text):
            raise RagEvalTechnicalAnswerError(answer_text)

        judge = await self._answer_judge.judge_answer(
            question=question,
            retrieved_entries=retrieved_entries,
            answer_text=answer_text,
        )

        latency_ms = int((perf_counter() - started) * 1000)
        deterministic_score = self._deterministic_score(
            question=question,
            retrieval=retrieval,
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
            retrieved_entries=retrieved_entries,
            answer_text=answer_text,
            top1_hit=retrieval.top1_hit,
            top3_hit=retrieval.top3_hit,
            top5_hit=retrieval.top5_hit,
            expected_entry_found=retrieval.expected_entry_found,
            wrong_entry_top1=retrieval.wrong_entry_top1,
            answer_supported=judge.answer_supported,
            hallucination_risk=judge.hallucination_risk,
            should_answer_passed=judge.should_answer_passed,
            score=final_score,
            classification=judge.classification,
            notes=judge.notes,
            latency_ms=latency_ms,
            judge_json=self._judge_json(
                judge.to_json() | {"mode": "answer_quality_eval"}
            ),
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
            retrieved_entries=[],
            answer_text="",
            top1_hit=False,
            top3_hit=False,
            top5_hit=False,
            expected_entry_found=False,
            wrong_entry_top1=bool(question.expected_entry_ids),
            answer_supported=False,
            hallucination_risk="high",
            should_answer_passed=not question.should_answer,
            score=0.0,
            notes=notes[:1000],
            latency_ms=0,
            judge_json=self._judge_json(
                {
                    "error": error_message,
                    "error_type": error_type,
                    "stage": stage,
                    "mode": self._mode,
                    "recovered": True,
                }
            ),
        )

    def _retrieval_only_result(
        self,
        *,
        run_id: str,
        question: RagEvalQuestion,
        retrieved_entries: list[RagEvalEvidenceEntry],
        retrieval: _RetrievalEvaluation,
        latency_ms: int,
    ) -> RagEvalResult:
        score = self._deterministic_score(question=question, retrieval=retrieval)
        classification = self._retrieval_failure_classification(
            question=question,
            retrieval=retrieval,
        )
        proposed_actions = (
            propose_knowledge_edit_actions(
                question=question,
                classification=classification,
            )
            if classification is not None
            else []
        )

        answer_supported = bool(
            retrieval.expected_entry_found
            or (not retrieval.expected_ids and not retrieval.wrong_entry_top1)
        )
        hallucination_risk: Literal["low", "medium", "high"] = "low"
        if retrieval.wrong_entry_top1:
            hallucination_risk = "high"
        elif retrieval.expected_ids and not retrieval.expected_entry_found:
            hallucination_risk = "medium"

        notes = self._retrieval_notes(retrieval)

        return RagEvalResult(
            id=new_eval_id("result"),
            run_id=run_id,
            question_id=question.id,
            question=question,
            retrieved_entries=retrieved_entries,
            answer_text="",
            top1_hit=retrieval.top1_hit,
            top3_hit=retrieval.top3_hit,
            top5_hit=retrieval.top5_hit,
            expected_entry_found=retrieval.expected_entry_found,
            wrong_entry_top1=retrieval.wrong_entry_top1,
            answer_supported=answer_supported,
            hallucination_risk=hallucination_risk,
            should_answer_passed=answer_supported
            if question.should_answer
            else not retrieval.wrong_entry_top1,
            score=score,
            classification=classification,
            proposed_actions=proposed_actions,
            notes=notes,
            latency_ms=latency_ms,
            judge_json=self._judge_json(
                {
                    "mode": "retrieval_eval",
                    "score_source": "deterministic_retrieval",
                    "expected_entry_ids": list(retrieval.expected_ids),
                    "retrieved_entry_ids": list(retrieval.retrieved_ids),
                    "expected_entry_rank": retrieval.expected_entry_rank,
                }
            ),
        )

    def _evaluate_retrieval(
        self,
        *,
        question: RagEvalQuestion,
        retrieved_ids: tuple[str, ...],
    ) -> _RetrievalEvaluation:
        expected_ids = frozenset(
            str(item).strip()
            for item in question.expected_entry_ids
            if str(item).strip()
        )
        top1_hit = bool(expected_ids.intersection(retrieved_ids[:1]))
        top3_hit = bool(expected_ids.intersection(retrieved_ids[:3]))
        top5_hit = bool(expected_ids.intersection(retrieved_ids[:5]))
        expected_entry_found = bool(expected_ids.intersection(retrieved_ids))
        wrong_entry_top1 = bool(
            retrieved_ids and (not expected_ids or retrieved_ids[0] not in expected_ids)
        )
        expected_entry_rank = self._expected_entry_rank(
            expected_ids=expected_ids,
            retrieved_ids=retrieved_ids,
        )
        return _RetrievalEvaluation(
            retrieved_ids=retrieved_ids,
            expected_ids=expected_ids,
            top1_hit=top1_hit,
            top3_hit=top3_hit,
            top5_hit=top5_hit,
            expected_entry_found=expected_entry_found,
            wrong_entry_top1=wrong_entry_top1,
            expected_entry_rank=expected_entry_rank,
        )

    @staticmethod
    def _expected_entry_rank(
        *,
        expected_ids: frozenset[str],
        retrieved_ids: tuple[str, ...],
    ) -> int | None:
        for index, retrieved_id in enumerate(retrieved_ids, start=1):
            if retrieved_id in expected_ids:
                return index
        return None

    def _deterministic_score(
        self,
        *,
        question: RagEvalQuestion,
        retrieval: _RetrievalEvaluation,
    ) -> float:
        if not retrieval.expected_ids:
            return 1.0 if not retrieval.retrieved_ids else 0.0

        if retrieval.top1_hit:
            return 1.0
        if retrieval.top3_hit:
            return 0.8
        if retrieval.top5_hit:
            return 0.6
        if retrieval.expected_entry_found:
            return 0.4
        return 0.0

    def _retrieval_failure_classification(
        self,
        *,
        question: RagEvalQuestion,
        retrieval: _RetrievalEvaluation,
    ) -> FailureClassification | None:
        if not retrieval.expected_ids:
            if retrieval.wrong_entry_top1:
                return FailureClassification(
                    stage=FailureStage.RETRIEVAL_ISSUE,
                    type=FailureType.WRONG_ENTRY_TOP1,
                    severity="medium",
                    root_cause=(
                        "Retriever returned an entry for a no-answer eval question."
                    ),
                    recommendations=(
                        "Review retrieval thresholds or no-answer routing for unsupported questions.",
                    ),
                    metadata={"retrieved_entry_ids": list(retrieval.retrieved_ids)},
                )
            return None

        if retrieval.wrong_entry_top1:
            return FailureClassification(
                stage=FailureStage.RETRIEVAL_ISSUE,
                type=FailureType.WRONG_ENTRY_TOP1,
                severity="high",
                root_cause=(
                    "Production retriever ranked a different entry above the expected entry."
                ),
                recommendations=(
                    "Attach this wording to the expected entry and rebuild its embedding.",
                ),
                metadata={
                    "expected_entry_ids": list(retrieval.expected_ids),
                    "retrieved_entry_ids": list(retrieval.retrieved_ids),
                    "expected_entry_rank": retrieval.expected_entry_rank,
                },
            )

        if not retrieval.expected_entry_found:
            return FailureClassification(
                stage=FailureStage.RETRIEVAL_ISSUE,
                type=FailureType.EXPECTED_ENTRY_NOT_FOUND,
                severity="high",
                root_cause="Production retriever did not return the expected entry.",
                recommendations=(
                    "Attach this wording to the expected entry and rebuild its embedding.",
                ),
                metadata={
                    "expected_entry_ids": list(retrieval.expected_ids),
                    "retrieved_entry_ids": list(retrieval.retrieved_ids),
                },
            )

        if not retrieval.top1_hit:
            return FailureClassification(
                stage=FailureStage.RETRIEVAL_ISSUE,
                type=FailureType.INSUFFICIENT_EVIDENCE,
                severity="medium",
                root_cause="Expected entry was retrieved but not ranked first.",
                recommendations=(
                    "Consider attaching this useful wording to the expected entry if it reflects real user phrasing.",
                ),
                metadata={
                    "expected_entry_ids": list(retrieval.expected_ids),
                    "retrieved_entry_ids": list(retrieval.retrieved_ids),
                    "expected_entry_rank": retrieval.expected_entry_rank,
                },
            )

        return None

    @staticmethod
    def _retrieval_notes(retrieval: _RetrievalEvaluation) -> str:
        if retrieval.top1_hit:
            return "Expected entry found at rank 1."
        if retrieval.expected_entry_rank is not None:
            return f"Expected entry found at rank {retrieval.expected_entry_rank}."
        return "Expected entry was not found in retrieved entries."

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
