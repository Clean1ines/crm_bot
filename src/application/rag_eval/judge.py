from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Literal, TypeAlias, cast

from src.application.rag_eval.ports import RagEvalJsonLlmPort
from src.application.rag_eval.schemas import (
    RagEvalAnswerJudgeResult,
    RagEvalChunk,
    RagEvalQuestion,
)


HallucinationRiskValue: TypeAlias = Literal["low", "medium", "high"]


class LlmRagEvalAnswerJudge:
    def __init__(self, *, llm: RagEvalJsonLlmPort) -> None:
        self._llm = llm

    async def judge_answer(
        self,
        *,
        question: RagEvalQuestion,
        retrieved_chunks: list[RagEvalChunk],
        answer_text: str,
    ) -> RagEvalAnswerJudgeResult:
        response = await self._llm.complete_json(
            system_prompt=self._system_prompt(),
            user_prompt=self._user_prompt(
                question=question,
                retrieved_chunks=retrieved_chunks,
                answer_text=answer_text,
            ),
            schema_name="rag_eval_answer_judge_v1",
        )
        return self._from_payload(response)

    def _system_prompt(self) -> str:
        return """
You are a strict RAG answer judge.

Evaluate whether the final bot answer is grounded in retrieved evidence
and follows expected behavior.

You must judge only from:
- question;
- expected evidence ids;
- expected answer summary;
- retrieved chunks;
- final answer.

Return strict JSON only.
Do not include hidden chain-of-thought.
""".strip()

    def _user_prompt(
        self,
        *,
        question: RagEvalQuestion,
        retrieved_chunks: list[RagEvalChunk],
        answer_text: str,
    ) -> str:
        question_json = json.dumps(
            question.to_json(),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        evidence_json = json.dumps(
            [chunk.to_json() for chunk in retrieved_chunks[:8]],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        answer_json = json.dumps(answer_text, ensure_ascii=False)

        return f"""
Question JSON:
{question_json}

Retrieved evidence JSON:
{evidence_json}

Final answer JSON string:
{answer_json}

Return one strict JSON object with exactly these fields:
{{
  "answer_supported": true,
  "hallucination_risk": "low",
  "missing_important_info": false,
  "client_friendly": true,
  "should_answer_passed": true,
  "notes": "short explanation without chain-of-thought",
  "score": 0.0
}}
""".strip()

    def _from_payload(self, payload: Mapping[str, object]) -> RagEvalAnswerJudgeResult:
        risk = str(payload.get("hallucination_risk") or "medium").strip()
        if risk not in {"low", "medium", "high"}:
            risk = "medium"

        return RagEvalAnswerJudgeResult(
            answer_supported=bool(payload.get("answer_supported")),
            hallucination_risk=cast(HallucinationRiskValue, risk),
            missing_important_info=bool(payload.get("missing_important_info")),
            client_friendly=bool(payload.get("client_friendly")),
            should_answer_passed=bool(payload.get("should_answer_passed")),
            notes=str(payload.get("notes") or "").strip()[:1000],
            score=self._score(payload.get("score")),
            metadata={"judge": "llm_rag_eval_answer_judge_v1"},
        )

    def _score(self, value: object) -> float:
        if isinstance(value, bool):
            return 0.0
        if not isinstance(value, int | float | str):
            return 0.0

        try:
            parsed = float(value)
        except ValueError:
            return 0.0

        return max(0.0, min(1.0, parsed))
