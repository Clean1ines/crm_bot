from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
import json

from src.contexts.knowledge_workbench.rag_eval.application.errors.workbench_rag_eval_question_generation_errors import (
    WorkbenchRagEvalQuestionGenerationError,
)
from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval import (
    GeneratedWorkbenchRagEvalQuestion,
    WorkbenchRagEvalQuestionKind,
    WorkbenchRagEvalQuestionSource,
)


PROMPT_PATH = Path("src/agent/prompts/workbench_rag_eval_question_variants.ru.txt")
WORKBENCH_RAG_EVAL_QUESTION_PROMPT_VERSION = (
    "workbench_rag_eval_question_variants.ru.v1"
)


@dataclass(frozen=True, slots=True)
class WorkbenchRagEvalQuestionGenerator:
    prompt_template: str
    prompt_version: str = WORKBENCH_RAG_EVAL_QUESTION_PROMPT_VERSION
    questions_per_entry: int = 10

    @classmethod
    def from_prompt_file(
        cls,
        *,
        prompt_path: Path = PROMPT_PATH,
    ) -> "WorkbenchRagEvalQuestionGenerator":
        return cls(
            prompt_template=prompt_path.read_text(encoding="utf-8"),
        )

    @property
    def generation_model(self) -> str:
        return "qwen/qwen3-32b"

    def build_provider_messages(
        self,
        *,
        claim: str,
        possible_questions: tuple[str, ...],
        exclusion_scope: str | None,
        evidence_block: str | None,
        triples: tuple[Mapping[str, object], ...],
    ) -> tuple[dict[str, str], dict[str, str]]:
        _require_text(claim, "claim")
        return (
            {"role": "system", "content": self.prompt_template},
            {
                "role": "user",
                "content": _input_payload_text(
                    claim=claim,
                    possible_questions=possible_questions,
                    exclusion_scope=exclusion_scope,
                    evidence_block=evidence_block,
                    triples=triples,
                    expected_question_count=self.questions_per_entry,
                ),
            },
        )

    def parse_questions_from_raw_text(
        self,
        *,
        raw_text: str,
        generation_model: str,
        generation_account_ref: str,
        generation_slot_index: int,
    ) -> tuple[GeneratedWorkbenchRagEvalQuestion, ...]:
        return _parse_generated_questions(
            raw_text=raw_text,
            generation_model=generation_model,
            prompt_version=self.prompt_version,
            generation_account_ref=generation_account_ref,
            generation_slot_index=generation_slot_index,
            expected_question_count=self.questions_per_entry,
        )


def _parse_generated_questions(
    *,
    raw_text: str,
    generation_model: str,
    prompt_version: str,
    generation_account_ref: str,
    generation_slot_index: int,
    expected_question_count: int,
) -> tuple[GeneratedWorkbenchRagEvalQuestion, ...]:
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise WorkbenchRagEvalQuestionGenerationError(
            "Question generation response is not valid JSON"
        ) from exc

    if not isinstance(payload, Mapping):
        raise WorkbenchRagEvalQuestionGenerationError(
            "Question generation response must be a JSON object"
        )
    questions_value = payload.get("questions")
    if not isinstance(questions_value, list):
        raise WorkbenchRagEvalQuestionGenerationError(
            "Question generation response.questions must be a list"
        )

    questions: list[GeneratedWorkbenchRagEvalQuestion] = []
    seen: set[str] = set()
    for index, item in enumerate(questions_value):
        if not isinstance(item, Mapping):
            raise WorkbenchRagEvalQuestionGenerationError(
                f"questions[{index}] must be an object"
            )
        raw_question = item.get("question")
        if not isinstance(raw_question, str):
            raise WorkbenchRagEvalQuestionGenerationError(
                f"questions[{index}].question must be a string"
            )
        question = raw_question.strip()
        if not question:
            continue
        normalized = " ".join(question.casefold().split())
        if normalized in seen:
            continue
        seen.add(normalized)

        raw_kind = item.get("question_kind")
        if not isinstance(raw_kind, str):
            raise WorkbenchRagEvalQuestionGenerationError(
                f"questions[{index}].question_kind must be a string"
            )
        try:
            kind = WorkbenchRagEvalQuestionKind(raw_kind)
        except ValueError as exc:
            raise WorkbenchRagEvalQuestionGenerationError(
                f"Invalid question_kind: {raw_kind}"
            ) from exc
        if kind is WorkbenchRagEvalQuestionKind.EXISTING_POSSIBLE_QUESTION:
            raise WorkbenchRagEvalQuestionGenerationError(
                "Generated questions cannot use existing_possible_question kind"
            )

        questions.append(
            GeneratedWorkbenchRagEvalQuestion(
                question=question,
                question_kind=kind,
                source=WorkbenchRagEvalQuestionSource.GENERATED,
                generation_model=generation_model,
                prompt_version=prompt_version,
                generation_account_ref=generation_account_ref,
                generation_slot_index=generation_slot_index,
            )
        )

    if len(questions) != expected_question_count:
        raise WorkbenchRagEvalQuestionGenerationError(
            "Question generation response must contain exactly "
            f"{expected_question_count} unique generated questions"
        )

    return tuple(questions)


def _input_payload_text(
    *,
    claim: str,
    possible_questions: tuple[str, ...],
    exclusion_scope: str | None,
    evidence_block: str | None,
    triples: tuple[Mapping[str, object], ...],
    expected_question_count: int,
) -> str:
    payload = {
        "claim": claim,
        "possible_questions": list(possible_questions),
        "exclusion_scope": exclusion_scope,
        "evidence_block": evidence_block,
        "triples": [dict(item) for item in triples],
        "expected_question_count": expected_question_count,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)


def _require_text(value: str, field_name: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{field_name} must be non-empty")
    return stripped
