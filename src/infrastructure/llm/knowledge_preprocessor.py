from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from groq import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AsyncGroq,
    RateLimitError,
)

from src.application.ports.knowledge_port import KnowledgePreprocessorPort
from src.domain.project_plane.json_types import JsonObject
from src.domain.project_plane.knowledge_preprocessing import (
    MODE_FAQ,
    ANSWER_MERGE_PROMPT_VERSION,
    KnowledgeAnswerMergeExecutionResult,
    KnowledgePreprocessingEntry,
    KnowledgePreprocessingExecutionResult,
    KnowledgePreprocessingMode,
    KnowledgePreprocessingValidationError,
    KnowledgeQuestionIntentCard,
    KnowledgeSemanticMergeExecutionResult,
    KnowledgeSemanticMergeGroup,
    KnowledgeSemanticMergeTighteningResult,
    SEMANTIC_MERGE_TIGHTENING_PROMPT_VERSION,
    parse_answer_merge_payload,
    parse_preprocessing_payload,
    parse_semantic_merge_tightening_payload,
    prompt_version_for_mode,
)
from src.domain.project_plane.model_usage_views import ModelUsageMeasurement
from src.infrastructure.config.settings import settings
from src.infrastructure.llm.groq_keyring import RotatingAsyncGroq
from src.infrastructure.logging.logger import get_logger

logger = get_logger(__name__)

STRICT_JSON_SYSTEM_MESSAGE = (
    "You are a strict JSON API. Return exactly one valid JSON object. "
    "Do not include markdown, code fences, explanations, comments, apologies, "
    "prefixes, suffixes, or multiple JSON objects. "
    "The first non-whitespace character must be { and the last non-whitespace "
    "character must be }."
)
KCD_LLM_RESPONSE_LOG_CHUNK_CHARS = 3500

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "agent" / "prompts"
FAQ_COMPILER_PROMPT_FILE = "knowledge_answer_compiler_faq.txt"
ANSWER_MERGE_PROMPT_FILE = "knowledge_answer_merge.txt"


def _usage_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


class GroqKnowledgePreprocessor(KnowledgePreprocessorPort):
    """Groq-backed adapter for optional knowledge preprocessing."""

    def __init__(
        self,
        *,
        client: AsyncGroq | None = None,
        model: str | None = None,
        max_chunks: int = 1,
        max_chunk_chars: int = 900,
    ) -> None:
        self._client = client or RotatingAsyncGroq()
        self._model = model or settings.GROQ_KNOWLEDGE_PREPROCESSING_MODEL
        self._max_chunks = max(1, max_chunks)
        self._max_chunk_chars = max(200, max_chunk_chars)

    @property
    def model_name(self) -> str:
        return self._model

    async def preprocess(
        self,
        *,
        mode: KnowledgePreprocessingMode,
        chunks: list[JsonObject],
        file_name: str,
        previous_question_intents: Sequence[KnowledgeQuestionIntentCard] = (),
    ) -> KnowledgePreprocessingExecutionResult:
        prompt_version = prompt_version_for_mode(mode)
        prompt = self._build_prompt(
            mode=mode,
            chunks=chunks,
            file_name=file_name,
            previous_question_intents=previous_question_intents,
        )

        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": STRICT_JSON_SYSTEM_MESSAGE},
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
                max_tokens=4000,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content or ""
            _log_llm_response(
                task="preprocess",
                mode=mode,
                model=self._model,
                prompt_version=prompt_version,
                content=content,
                response=response,
            )
            result = parse_preprocessing_payload(
                content, mode=mode, model=self._model, prompt_version=prompt_version
            )
            return KnowledgePreprocessingExecutionResult(
                result=result,
                usage=_response_usage_measurement(
                    response=response,
                    model=self._model,
                    prompt=prompt,
                    content=content,
                ),
            )
        except (
            APIConnectionError,
            APIError,
            APITimeoutError,
            RateLimitError,
            AttributeError,
            IndexError,
            TypeError,
            ValueError,
            KnowledgePreprocessingValidationError,
        ) as exc:
            logger.warning(
                "Knowledge preprocessing failed",
                extra={
                    "mode": mode,
                    "model": self._model,
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:300],
                },
            )
            raise

    async def merge_known_answer(
        self,
        *,
        mode: KnowledgePreprocessingMode,
        file_name: str,
        known_intent: KnowledgePreprocessingEntry,
        incoming_fragment: KnowledgePreprocessingEntry,
    ) -> KnowledgeAnswerMergeExecutionResult:
        prompt_version = ANSWER_MERGE_PROMPT_VERSION
        prompt = self._build_answer_merge_prompt(
            mode=mode,
            file_name=file_name,
            known_intent=known_intent,
            incoming_fragment=incoming_fragment,
        )

        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": STRICT_JSON_SYSTEM_MESSAGE},
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
                max_tokens=1600,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content or ""
            _log_llm_response(
                task="answer_merge",
                mode=mode,
                model=self._model,
                prompt_version=prompt_version,
                content=content,
                response=response,
            )
            merge_allowed, answer, question_variants = parse_answer_merge_payload(
                content
            )
            return KnowledgeAnswerMergeExecutionResult(
                merge_allowed=merge_allowed,
                answer=answer,
                question_variants=question_variants,
                usage=_response_usage_measurement(
                    response=response,
                    model=self._model,
                    prompt=prompt,
                    content=content,
                ),
            )
        except (
            APIConnectionError,
            APIError,
            APITimeoutError,
            RateLimitError,
            AttributeError,
            IndexError,
            TypeError,
            ValueError,
            KnowledgePreprocessingValidationError,
        ) as exc:
            logger.warning(
                "Knowledge answer merge failed",
                extra={
                    "mode": mode,
                    "model": self._model,
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:300],
                },
            )
            raise

    async def tighten_semantic_merges(
        self,
        *,
        mode: KnowledgePreprocessingMode,
        file_name: str,
        groups: Sequence[KnowledgeSemanticMergeGroup],
        existing_project_titles: Sequence[str] = (),
    ) -> KnowledgeSemanticMergeExecutionResult:
        prompt_version = SEMANTIC_MERGE_TIGHTENING_PROMPT_VERSION

        if not groups:
            return KnowledgeSemanticMergeExecutionResult(
                result=KnowledgeSemanticMergeTighteningResult(
                    mode=mode,
                    prompt_version=prompt_version,
                    model=self._model,
                    decisions=(),
                    metrics={"group_count": 0},
                ),
                usage=None,
            )

        prompt = self._build_semantic_merge_tightening_prompt(
            mode=mode,
            file_name=file_name,
            groups=groups,
            existing_project_titles=existing_project_titles,
        )

        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": STRICT_JSON_SYSTEM_MESSAGE},
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
                max_tokens=3000,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content or ""
            _log_llm_response(
                task="semantic_merge_tightening",
                mode=mode,
                model=self._model,
                prompt_version=prompt_version,
                content=content,
                response=response,
            )
            result = parse_semantic_merge_tightening_payload(
                content,
                mode=mode,
                model=self._model,
                prompt_version=prompt_version,
            )
            return KnowledgeSemanticMergeExecutionResult(
                result=result,
                usage=_response_usage_measurement(
                    response=response,
                    model=self._model,
                    prompt=prompt,
                    content=content,
                ),
            )
        except (
            APIConnectionError,
            APIError,
            APITimeoutError,
            RateLimitError,
            AttributeError,
            IndexError,
            TypeError,
            ValueError,
            KnowledgePreprocessingValidationError,
        ) as exc:
            logger.warning(
                "Knowledge semantic merge tightening failed",
                extra={
                    "mode": mode,
                    "model": self._model,
                    "group_count": len(groups),
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:300],
                },
            )
            raise

    def _build_answer_merge_prompt(
        self,
        *,
        mode: KnowledgePreprocessingMode,
        file_name: str,
        known_intent: KnowledgePreprocessingEntry,
        incoming_fragment: KnowledgePreprocessingEntry,
    ) -> str:
        instruction = _load_answer_merge_prompt()
        merge_payload = {
            "file_name": file_name,
            "mode": mode,
            "known_intent": {
                "intent_id": incoming_fragment.known_intent_id,
                "canonical_question": known_intent.canonical_question
                or _first_question(known_intent),
                "question_variants": list(known_intent.questions),
                "answer": known_intent.answer,
            },
            "incoming_fragment": {
                "canonical_question": incoming_fragment.canonical_question
                or _first_question(incoming_fragment),
                "question_variants": list(incoming_fragment.questions),
                "answer_fragment": incoming_fragment.answer,
                "source_excerpt": incoming_fragment.source_excerpt,
                "source_chunk_indexes": list(incoming_fragment.source_chunk_indexes),
            },
        }
        return f"{instruction}\n{json.dumps(merge_payload, ensure_ascii=False)}"

    def _build_semantic_merge_tightening_prompt(
        self,
        *,
        mode: KnowledgePreprocessingMode,
        file_name: str,
        groups: Sequence[KnowledgeSemanticMergeGroup],
        existing_project_titles: Sequence[str] = (),
    ) -> str:
        compact_project_titles = [
            " ".join(str(title).strip().split())
            for title in existing_project_titles
            if str(title).strip()
        ][:300]
        merge_payload = {
            "file_name": file_name,
            "mode": mode,
            "existing_project_titles": compact_project_titles,
            "suspect_groups": [group.to_payload() for group in groups],
        }

        return (
            "SEMANTIC MERGE TIGHTENING TASK:\n"
            "Return exactly one JSON object and nothing else.\n\n"
            "Purpose:\n"
            "- You receive groups of already grounded canonical-entry candidates.\n"
            "- Each group is only a suspect duplicate group, not a command to merge.\n"
            "- same answer intent / stable user information need is the only valid merge target.\n"
            "- Decide whether candidates in each group are truly that same answer intent.\n"
            "- Treat answer intent as: primary user question, realistic question samples, compact answer digest, tags, and grounded answer facts.\n"
            "- Do not use embedding_text as the primary identity signal; it is only retrieval helper text.\n"
            "- Merge only when the same user information need should retrieve one consolidated canonical answer.\n"
            "- Keep separate when candidates are related but answer different intents, constraints, audiences, operations, policies, or stages.\n"
            "- Shared words such as assistant, business, manager, request, client, CRM or bot are never enough to merge.\n"
            "- Groups are pairwise by design: compare the two candidates directly, not by broad topic similarity.\n\n"
            "Schema:\n"
            "{\n"
            '  "decisions": [\n'
            "    {\n"
            '      "group_id": "...",\n'
            '      "action": "merge | keep_separate",\n'
            '      "candidate_ids": ["..."],\n'
            '      "survivor_title": "...",\n'
            '      "merged_embedding_text": "..."\n'
            "    }\n"
            "  ]\n"
            "}\n\n"
            "Rules for action=merge:\n"
            "- candidate_ids MUST contain all candidates being collapsed.\n"
            "- survivor_title MUST be exactly one concise canonical title.\n"
            "- merged_embedding_text MUST be a compact replacement canonical retrieval text for the shared user question/intent.\n"
            "- Do NOT concatenate candidate answers or candidate embedding_text values.\n"
            "- Do NOT append old answer + new answer; return one compressed replacement.\n"
            "- If candidates are A and A+B for the same intent, return A+B once, not A+A+B.\n"
            "- It MUST be shorter than the combined candidate answer + embedding_text unless preserving distinct grounded constraints requires otherwise.\n"
            "- Preserve grounded facts, limitations, product terms, handoff rules, prices, dates, and negative constraints exactly once.\n"
            "- Remove exact and near-duplicate phrases, repeated sentences, repeated examples, repeated benefits, and repeated intent variants.\n"
            "- If one candidate only adds a minor clarification to the same answer, fold that clarification into the canonical wording once.\n"
            "- Do not invent facts.\n\n"
            "Rules for action=keep_separate:\n"
            "- Use when candidates are related but not the same answer intent / stable information need.\n"
            "- In particular, keep separate price vs onboarding, refund vs handoff, audience vs product description, CRM integration vs generic product, availability vs dialog history.\n"
            "- candidate_ids MUST contain the candidates considered for that decision.\n"
            "- survivor_title and merged_embedding_text MAY be empty.\n\n"
            "Project-level title context:\n"
            "- existing_project_titles are already published project answers.\n"
            "- Prefer a survivor_title compatible with an existing project title when the meaning is the same.\n"
            "- Do not merge with existing_project_titles here; only use them for naming consistency.\n\n"
            "STRICT OUTPUT CONTRACT:\n"
            "- Return exactly one JSON object.\n"
            "- The first non-whitespace character must be { and the last non-whitespace character must be }.\n"
            "- Do not return markdown, explanation, entries[], source refs, or full answers.\n\n"
            "NOW PROCESS THIS JSON. Return ONLY the JSON result:\n"
            f"{json.dumps(merge_payload, ensure_ascii=False)}"
        )

    def _build_prompt(
        self,
        *,
        mode: KnowledgePreprocessingMode,
        chunks: list[JsonObject],
        file_name: str,
        previous_question_intents: Sequence[KnowledgeQuestionIntentCard] = (),
    ) -> str:
        instruction = _load_mode_prompt(mode)
        known_question_intents = [
            card.to_payload() for card in previous_question_intents
        ][:8]
        source_payload = {
            "file_name": file_name,
            "mode": mode,
            "known_question_intents": known_question_intents,
            "chunks": [
                {
                    "index": index,
                    "content": str(chunk.get("content") or "")[: self._max_chunk_chars],
                }
                for index, chunk in enumerate(chunks[: self._max_chunks])
            ],
        }
        return f"{instruction}\n{json.dumps(source_payload, ensure_ascii=False)}"


def _log_llm_response(
    *,
    task: str,
    mode: KnowledgePreprocessingMode,
    model: str,
    prompt_version: str,
    content: str,
    response: object,
) -> None:
    raw_choices = getattr(response, "choices", ())
    finish_reason = ""
    if isinstance(raw_choices, Sequence) and raw_choices:
        finish_reason = str(getattr(raw_choices[0], "finish_reason", "") or "")

    base_extra = {
        "task": task,
        "mode": mode,
        "model": model,
        "prompt_version": prompt_version,
        "content_length": len(content),
        "finish_reason": finish_reason,
    }

    if not content:
        logger.warning("Knowledge LLM returned empty JSON response", extra=base_extra)
        return

    for chunk_index, start in enumerate(
        range(0, len(content), KCD_LLM_RESPONSE_LOG_CHUNK_CHARS),
        start=1,
    ):
        chunk = content[start : start + KCD_LLM_RESPONSE_LOG_CHUNK_CHARS]
        logger.info(
            "Knowledge LLM raw JSON response",
            extra={
                **base_extra,
                "chunk_index": chunk_index,
                "raw_response_chunk": chunk,
            },
        )


def _load_mode_prompt(mode: KnowledgePreprocessingMode) -> str:
    if mode != MODE_FAQ:
        raise KnowledgePreprocessingValidationError(
            f"Knowledge answer compiler is only available for FAQ mode, got: {mode}"
        )
    return (PROMPTS_DIR / FAQ_COMPILER_PROMPT_FILE).read_text(encoding="utf-8")


def _load_answer_merge_prompt() -> str:
    return (PROMPTS_DIR / ANSWER_MERGE_PROMPT_FILE).read_text(encoding="utf-8")


def _first_question(entry: KnowledgePreprocessingEntry) -> str:
    return next((question for question in entry.questions if question), entry.title)


def _response_usage_measurement(
    *,
    response: object,
    model: str,
    prompt: str,
    content: str,
) -> ModelUsageMeasurement:
    usage = getattr(response, "usage", None)
    prompt_tokens = _usage_int(getattr(usage, "prompt_tokens", None))
    completion_tokens = _usage_int(getattr(usage, "completion_tokens", None))
    total_tokens = _usage_int(getattr(usage, "total_tokens", None))

    has_exact_usage = all(
        isinstance(value, int) and not isinstance(value, bool)
        for value in (prompt_tokens, completion_tokens, total_tokens)
    )

    if has_exact_usage:
        return ModelUsageMeasurement(
            provider="groq",
            model=model,
            usage_type="llm",
            tokens_input=int(prompt_tokens or 0),
            tokens_output=int(completion_tokens or 0),
            tokens_total=int(total_tokens or 0),
            estimated_cost_usd=None,
            metadata={"is_estimated": False, "source_kind": "knowledge_preprocessing"},
        )

    estimated_prompt_tokens = max(1, (len(prompt) + 3) // 4)
    estimated_completion_tokens = max(1, (len(content) + 3) // 4)
    return ModelUsageMeasurement(
        provider="groq",
        model=model,
        usage_type="llm",
        tokens_input=estimated_prompt_tokens,
        tokens_output=estimated_completion_tokens,
        tokens_total=estimated_prompt_tokens + estimated_completion_tokens,
        estimated_cost_usd=None,
        metadata={"is_estimated": True, "source_kind": "knowledge_preprocessing"},
    )
