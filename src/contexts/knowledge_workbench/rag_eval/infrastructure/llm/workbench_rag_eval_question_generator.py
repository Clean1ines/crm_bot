from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from hashlib import sha256
import json

from src.contexts.llm_runtime.application.ports.llm_dispatch_executor_port import (
    LlmDispatchExecutionInput,
    LlmDispatchExecutionStatus,
    LlmDispatchExecutorPort,
)
from src.contexts.llm_runtime.domain.capacity.llm_model_route_catalog import (
    LlmModelExecutionSettings,
)
from src.contexts.knowledge_workbench.rag_eval.application.errors.workbench_rag_eval_question_generation_errors import (
    WorkbenchRagEvalQuestionGenerationError,
)
from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval import (
    GeneratedWorkbenchRagEvalQuestion,
    WorkbenchRagEvalQuestionKind,
    WorkbenchRagEvalQuestionSource,
)
from src.contexts.knowledge_workbench.rag_eval.application.policies.workbench_rag_eval_question_generation_route_policy import (
    WorkbenchRagEvalQuestionGenerationRouteCandidate,
    WorkbenchRagEvalQuestionGenerationRoutePolicy,
)
from src.contexts.knowledge_workbench.rag_eval.application.ports.workbench_rag_eval_question_generator_port import (
    WorkbenchRagEvalQuestionGeneratorPort,
)


PROMPT_PATH = Path("src/agent/prompts/workbench_rag_eval_question_variants.ru.txt")
WORKBENCH_RAG_EVAL_QUESTION_PROMPT_VERSION = (
    "workbench_rag_eval_question_variants.ru.v1"
)


@dataclass(frozen=True, slots=True)
class WorkbenchRagEvalQuestionGenerator(WorkbenchRagEvalQuestionGeneratorPort):
    llm_dispatch_executor: LlmDispatchExecutorPort
    prompt_template: str
    prompt_version: str = WORKBENCH_RAG_EVAL_QUESTION_PROMPT_VERSION
    max_questions_per_entry: int = 20

    @classmethod
    def from_prompt_file(
        cls,
        *,
        llm_dispatch_executor: LlmDispatchExecutorPort,
        prompt_path: Path = PROMPT_PATH,
    ) -> "WorkbenchRagEvalQuestionGenerator":
        return cls(
            llm_dispatch_executor=llm_dispatch_executor,
            prompt_template=prompt_path.read_text(encoding="utf-8"),
        )

    @property
    def generation_model(self) -> str:
        return WorkbenchRagEvalQuestionGenerationRoutePolicy.default().primary_model_ref

    async def generate_questions_for_entry(
        self,
        *,
        claim: str,
        possible_questions: tuple[str, ...],
        exclusion_scope: str | None,
        evidence_block: str | None,
        triples: tuple[Mapping[str, object], ...],
        route_candidate: WorkbenchRagEvalQuestionGenerationRouteCandidate,
    ) -> tuple[GeneratedWorkbenchRagEvalQuestion, ...]:
        claim = _require_text(claim, "claim")
        if self.max_questions_per_entry < 1:
            raise ValueError("max_questions_per_entry must be positive")

        result = await self.llm_dispatch_executor.execute_dispatch(
            LlmDispatchExecutionInput(
                attempt_id=_stable_id(
                    "workbench-rag-eval-qgen-attempt",
                    claim,
                    route_candidate.model_ref,
                    route_candidate.account_ref,
                ),
                work_item_id=_stable_id("workbench-rag-eval-qgen-work", claim),
                attempt_number=1,
                dispatch_payload=self._dispatch_payload(
                    claim=claim,
                    possible_questions=possible_questions,
                    exclusion_scope=exclusion_scope,
                    evidence_block=evidence_block,
                    triples=triples,
                    route_candidate=route_candidate,
                ),
                started_at=datetime.now(timezone.utc),
            )
        )
        if result.status is not LlmDispatchExecutionStatus.SUCCEEDED:
            raise WorkbenchRagEvalQuestionGenerationError(
                f"Question generation failed on {route_candidate.model_ref}/"
                f"{route_candidate.account_ref}: {result.error_kind or result.status.value}"
            )
        if result.output_payload is None:
            raise WorkbenchRagEvalQuestionGenerationError(
                "Question generation succeeded without output payload"
            )

        raw_text = result.output_payload.get("raw_text")
        if not isinstance(raw_text, str):
            raise WorkbenchRagEvalQuestionGenerationError(
                "Question generation output payload missing raw_text"
            )

        return _parse_generated_questions(
            raw_text=raw_text,
            generation_model=route_candidate.model_ref,
            prompt_version=self.prompt_version,
            generation_account_ref=route_candidate.account_ref,
            generation_slot_index=route_candidate.slot_index,
            max_questions=self.max_questions_per_entry,
        )

    def _dispatch_payload(
        self,
        *,
        claim: str,
        possible_questions: tuple[str, ...],
        exclusion_scope: str | None,
        evidence_block: str | None,
        triples: tuple[Mapping[str, object], ...],
        route_candidate: WorkbenchRagEvalQuestionGenerationRouteCandidate,
    ) -> Mapping[str, object]:
        return {
            "work_item_id": _stable_id("workbench-rag-eval-qgen-work", claim),
            "schedule_payload": {
                "provider_messages": [
                    {
                        "role": "system",
                        "content": self.prompt_template,
                    },
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
                ],
            },
            "llm_allocation": {
                "provider": route_candidate.provider,
                "account_ref": route_candidate.account_ref,
                "model_ref": route_candidate.model_ref,
                "slot_index": route_candidate.slot_index,
            },
            "llm_execution_settings": _execution_settings_payload(
                route_candidate.execution_settings
            ),
            "capacity_metadata": {
                "input_token_limit": route_candidate.input_token_limit,
                "output_token_limit": route_candidate.output_token_limit,
                "route_role": route_candidate.role.value,
            },
        }


def _parse_generated_questions(
    *,
    raw_text: str,
    generation_model: str,
    prompt_version: str,
    generation_account_ref: str,
    generation_slot_index: int,
    max_questions: int,
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
        if len(questions) >= max_questions:
            break
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
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)


def _execution_settings_payload(
    settings: LlmModelExecutionSettings,
) -> Mapping[str, object]:
    return {
        "reasoning_enabled": settings.reasoning_enabled,
        "reasoning_effort": settings.reasoning_effort,
    }


def _stable_id(*parts: str) -> str:
    return sha256(":".join(parts).encode("utf-8")).hexdigest()


def _require_text(value: str, field_name: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{field_name} must be non-empty")
    return stripped
