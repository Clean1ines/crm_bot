from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
import json
import unicodedata

from src.contexts.knowledge_workbench.rag_eval.application.errors.workbench_rag_eval_question_generation_errors import (
    WorkbenchRagEvalQuestionGenerationError,
)
from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval import (
    GeneratedWorkbenchRagEvalQuestion,
    WorkbenchRagEvalQuestionAmbiguityRisk,
    WorkbenchRagEvalQuestionKind,
    WorkbenchRagEvalQuestionSource,
)


PROMPT_PATH = Path("src/agent/prompts/workbench_rag_eval_question_variants.ru.v2.txt")
WORKBENCH_RAG_EVAL_QUESTION_PROMPT_VERSION = (
    "workbench_rag_eval_question_variants.ru.v2"
)
WORKBENCH_RAG_EVAL_QUESTION_CONTRACT_VERSION = "workbench_rag_eval_questions.v2"

_REQUIRED_DISTRIBUTION = {
    WorkbenchRagEvalQuestionKind.DIRECT_PARAPHRASE: 2,
    WorkbenchRagEvalQuestionKind.LEXICAL_VARIANT: 2,
    WorkbenchRagEvalQuestionKind.NAIVE_USER: 2,
    WorkbenchRagEvalQuestionKind.ENTITY_FIRST: 1,
    WorkbenchRagEvalQuestionKind.ACTION_FIRST: 1,
    WorkbenchRagEvalQuestionKind.CONSTRAINT_FIRST: 1,
    WorkbenchRagEvalQuestionKind.DOMAIN_SPECIFIC: 1,
}
_ALLOWED_GENERATED_KINDS = frozenset(_REQUIRED_DISTRIBUTION)


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
        return cls(prompt_template=prompt_path.read_text(encoding="utf-8"))

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
        existing_possible_questions: tuple[str, ...] = (),
    ) -> tuple[GeneratedWorkbenchRagEvalQuestion, ...]:
        return _parse_generated_questions(
            raw_text=raw_text,
            generation_model=generation_model,
            prompt_version=self.prompt_version,
            generation_account_ref=generation_account_ref,
            generation_slot_index=generation_slot_index,
            existing_possible_questions=existing_possible_questions,
        )


def _parse_generated_questions(
    *,
    raw_text: str,
    generation_model: str,
    prompt_version: str,
    generation_account_ref: str,
    generation_slot_index: int,
    existing_possible_questions: tuple[str, ...],
) -> tuple[GeneratedWorkbenchRagEvalQuestion, ...]:
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise WorkbenchRagEvalQuestionGenerationError(
            "INVALID_JSON: response is not valid JSON"
        ) from exc

    if not isinstance(payload, Mapping):
        raise WorkbenchRagEvalQuestionGenerationError(
            "INVALID_ROOT: response must be a JSON object"
        )

    contract_version = payload.get("contract_version")
    if contract_version != WORKBENCH_RAG_EVAL_QUESTION_CONTRACT_VERSION:
        raise WorkbenchRagEvalQuestionGenerationError(
            "INVALID_CONTRACT_VERSION: expected "
            f"{WORKBENCH_RAG_EVAL_QUESTION_CONTRACT_VERSION}"
        )

    questions_value = payload.get("questions")
    if not isinstance(questions_value, list):
        raise WorkbenchRagEvalQuestionGenerationError(
            "INVALID_ROOT: questions must be a list"
        )
    if len(questions_value) != 10:
        raise WorkbenchRagEvalQuestionGenerationError(
            "INVALID_QUESTION_COUNT: questions must contain exactly 10 items"
        )

    normalized_existing = {
        _normalize_question(question)
        for question in existing_possible_questions
        if isinstance(question, str) and question.strip()
    }

    questions: list[GeneratedWorkbenchRagEvalQuestion] = []
    exact_seen: set[str] = set()
    normalized_seen: set[str] = set()
    distribution: Counter[WorkbenchRagEvalQuestionKind] = Counter()

    for index, item in enumerate(questions_value):
        if not isinstance(item, Mapping):
            raise WorkbenchRagEvalQuestionGenerationError(
                f"INVALID_ITEM: questions[{index}] must be an object"
            )

        question = _required_non_empty_string(
            item.get("question"),
            field_name=f"questions[{index}].question",
        )
        raw_kind = _required_non_empty_string(
            item.get("question_kind"),
            field_name=f"questions[{index}].question_kind",
        )
        rationale = _required_non_empty_string(
            item.get("rationale"),
            field_name=f"questions[{index}].rationale",
        )

        try:
            kind = WorkbenchRagEvalQuestionKind(raw_kind)
        except ValueError as exc:
            raise WorkbenchRagEvalQuestionGenerationError(
                f"INVALID_ITEM: unknown question_kind {raw_kind!r}"
            ) from exc
        if kind not in _ALLOWED_GENERATED_KINDS:
            raise WorkbenchRagEvalQuestionGenerationError(
                f"INVALID_ITEM: question_kind {raw_kind!r} is not allowed in V2"
            )

        promotion_eligible = item.get("promotion_eligible")
        if not isinstance(promotion_eligible, bool):
            raise WorkbenchRagEvalQuestionGenerationError(
                f"INVALID_ITEM: questions[{index}].promotion_eligible must be bool"
            )

        raw_risk = _required_non_empty_string(
            item.get("ambiguity_risk"),
            field_name=f"questions[{index}].ambiguity_risk",
        )
        try:
            ambiguity_risk = WorkbenchRagEvalQuestionAmbiguityRisk(raw_risk)
        except ValueError as exc:
            raise WorkbenchRagEvalQuestionGenerationError(
                f"INVALID_ITEM: unknown ambiguity_risk {raw_risk!r}"
            ) from exc

        if (
            promotion_eligible
            and ambiguity_risk is not WorkbenchRagEvalQuestionAmbiguityRisk.LOW
        ):
            raise WorkbenchRagEvalQuestionGenerationError(
                "INVALID_PROMOTION_ELIGIBILITY: promotion_eligible=true "
                "requires ambiguity_risk=low"
            )

        if question in exact_seen:
            raise WorkbenchRagEvalQuestionGenerationError(
                f"DUPLICATE_GENERATED_QUESTION: exact duplicate {question!r}"
            )
        exact_seen.add(question)

        normalized = _normalize_question(question)
        if normalized in normalized_seen:
            raise WorkbenchRagEvalQuestionGenerationError(
                f"DUPLICATE_GENERATED_QUESTION: normalized duplicate {question!r}"
            )
        if normalized in normalized_existing:
            raise WorkbenchRagEvalQuestionGenerationError(
                f"DUPLICATE_EXISTING_QUESTION: {question!r}"
            )
        normalized_seen.add(normalized)

        distribution[kind] += 1
        questions.append(
            GeneratedWorkbenchRagEvalQuestion(
                question=question,
                question_kind=kind,
                source=WorkbenchRagEvalQuestionSource.GENERATED,
                generation_model=generation_model,
                prompt_version=prompt_version,
                contract_version=contract_version,
                promotion_eligible=promotion_eligible,
                ambiguity_risk=ambiguity_risk,
                generation_rationale=rationale,
                generation_account_ref=generation_account_ref,
                generation_slot_index=generation_slot_index,
            )
        )

    if dict(distribution) != _REQUIRED_DISTRIBUTION:
        actual = {
            kind.value: distribution.get(kind, 0) for kind in _REQUIRED_DISTRIBUTION
        }
        expected = {kind.value: count for kind, count in _REQUIRED_DISTRIBUTION.items()}
        raise WorkbenchRagEvalQuestionGenerationError(
            f"INVALID_KIND_DISTRIBUTION: expected={expected}, actual={actual}"
        )

    return tuple(questions)


def _input_payload_text(
    *,
    claim: str,
    possible_questions: tuple[str, ...],
    exclusion_scope: str | None,
    evidence_block: str | None,
    triples: tuple[Mapping[str, object], ...],
) -> str:
    payload = {
        "claim": claim,
        "possible_questions": list(possible_questions),
        "exclusion_scope": exclusion_scope,
        "evidence_block": evidence_block,
        "triples": [dict(item) for item in triples],
        "target_language": "ru",
        "required_question_count": 10,
        "required_distribution": {
            kind.value: count for kind, count in _REQUIRED_DISTRIBUTION.items()
        },
        "contract_version": WORKBENCH_RAG_EVAL_QUESTION_CONTRACT_VERSION,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)


def _normalize_question(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold().strip()
    characters: list[str] = []
    previous_was_space = False

    for character in normalized:
        category = unicodedata.category(character)
        if character.isspace() or category.startswith("P"):
            if characters and not previous_was_space:
                characters.append(" ")
                previous_was_space = True
            continue
        characters.append(character)
        previous_was_space = False

    return "".join(characters).strip()


def _required_non_empty_string(value: object, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise WorkbenchRagEvalQuestionGenerationError(
            f"INVALID_ITEM: {field_name} must be string"
        )
    stripped = value.strip()
    if not stripped:
        raise WorkbenchRagEvalQuestionGenerationError(
            f"INVALID_ITEM: {field_name} must be non-empty"
        )
    return stripped


def _require_text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{field_name} must be non-empty")
    return stripped
