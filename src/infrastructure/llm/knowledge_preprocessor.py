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
    MODE_INSTRUCTION,
    MODE_PRICE_LIST,
    KnowledgeEmbeddingTextMergeExecutionResult,
    KnowledgePreprocessingExecutionResult,
    KnowledgePreprocessingMode,
    KnowledgePreprocessingValidationError,
    KnowledgeSemanticMergeExecutionResult,
    KnowledgeSemanticMergeGroup,
    KnowledgeSemanticMergeTighteningResult,
    SEMANTIC_MERGE_TIGHTENING_PROMPT_VERSION,
    parse_embedding_text_merge_payload,
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
MODE_PROMPT_FILES = {
    MODE_FAQ: "knowledge_preprocess_faq.txt",
    MODE_PRICE_LIST: "knowledge_preprocess_price_list.txt",
    MODE_INSTRUCTION: "knowledge_preprocess_instruction.txt",
}


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
        previous_entry_titles: Sequence[str] = (),
    ) -> KnowledgePreprocessingExecutionResult:
        prompt_version = prompt_version_for_mode(mode)
        prompt = self._build_prompt(
            mode=mode,
            chunks=chunks,
            file_name=file_name,
            previous_entry_titles=previous_entry_titles,
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

    async def merge_embedding_text(
        self,
        *,
        mode: KnowledgePreprocessingMode,
        file_name: str,
        title: str,
        existing_embedding_text: str,
        incoming_embedding_text: str,
    ) -> KnowledgeEmbeddingTextMergeExecutionResult:
        prompt_version = prompt_version_for_mode(mode)
        prompt = self._build_embedding_text_merge_prompt(
            mode=mode,
            file_name=file_name,
            title=title,
            existing_embedding_text=existing_embedding_text,
            incoming_embedding_text=incoming_embedding_text,
        )

        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": STRICT_JSON_SYSTEM_MESSAGE},
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
                max_tokens=900,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content or ""
            _log_llm_response(
                task="merge_embedding_text",
                mode=mode,
                model=self._model,
                prompt_version=prompt_version,
                content=content,
                response=response,
            )
            embedding_text = parse_embedding_text_merge_payload(content)
            return KnowledgeEmbeddingTextMergeExecutionResult(
                embedding_text=embedding_text,
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
                "Knowledge embedding text merge failed",
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

    def _build_embedding_text_merge_prompt(
        self,
        *,
        mode: KnowledgePreprocessingMode,
        file_name: str,
        title: str,
        existing_embedding_text: str,
        incoming_embedding_text: str,
    ) -> str:
        compact_existing = " ".join(existing_embedding_text.split())[:2400]
        compact_incoming = " ".join(incoming_embedding_text.split())[:1600]
        merge_payload = {
            "file_name": file_name,
            "mode": mode,
            "title": title,
            "existing_embedding_text": compact_existing,
            "incoming_embedding_text": compact_incoming,
        }

        return (
            "EMBEDDING TEXT MERGE TASK:\n"
            "Return exactly one JSON object and nothing else.\n\n"
            "Schema:\n"
            '{"embedding_text": "..."}\n\n'
            "Rules:\n"
            "- Merge only existing_embedding_text and incoming_embedding_text.\n"
            "- Return one dense Russian/English retrieval text for semantic search.\n"
            "- Preserve grounded facts, limitations, conditions, product terms, prices, dates, escalation rules, and user-facing wording from both inputs.\n"
            "- Remove exact duplicates and near-duplicate phrases.\n"
            "- Do not invent facts.\n"
            "- Do not return title, answer, source_excerpt, questions, synonyms, tags, entries, markdown, or explanation.\n"
            "- Keep the result detailed but compact.\n\n"
            "STRICT OUTPUT CONTRACT:\n"
            "- Return exactly one JSON object.\n"
            "- The only allowed key is embedding_text.\n"
            "- The first non-whitespace character must be { and the last non-whitespace character must be }.\n\n"
            "NOW MERGE THIS JSON. Return ONLY the JSON result:\n"
            f"{json.dumps(merge_payload, ensure_ascii=False)}"
        )

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
            "- Decide whether candidates in each group are truly the same answer meaning.\n"
            "- Merge only when one user question should retrieve one consolidated answer.\n"
            "- Keep separate when candidates answer different user intents, constraints, audiences, or operations.\n\n"
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
            "- merged_embedding_text MUST synthesize retrieval wording from all merged candidates; do not concatenate candidates.\n"
            "- It MUST be shorter than the combined candidate embedding_text unless preserving distinct grounded constraints requires otherwise.\n"
            "- Preserve grounded facts, limitations, product terms, handoff rules, prices, dates, and negative constraints.\n"
            "- Remove exact and near-duplicate phrases, repeated sentences, repeated examples, and repeated intent variants.\n"
            "- Do not invent facts.\n\n"
            "Rules for action=keep_separate:\n"
            "- Use when candidates are related but not the same answer meaning.\n"
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
        previous_entry_titles: Sequence[str] = (),
    ) -> str:
        instruction = _load_mode_prompt(mode)
        previous_titles = [
            " ".join(str(title).strip().split())
            for title in previous_entry_titles
            if str(title).strip()
        ][:80]
        source_payload = {
            "file_name": file_name,
            "mode": mode,
            "previous_answer_titles": previous_titles,
            "chunks": [
                {
                    "index": index,
                    "content": str(chunk.get("content") or "")[: self._max_chunk_chars],
                }
                for index, chunk in enumerate(chunks[: self._max_chunks])
            ],
        }
        carryover_instruction = (
            "CROSS-CHUNK COMPILER CONTEXT:\n"
            "- previous_answer_titles contains answer meanings already extracted "
            "from earlier technical source chunks.\n"
            "- Before creating a new entry, check whether the current source "
            "expands or refines one of those meanings.\n"
            "- If it is the same meaning, reuse the exact previous title and "
            "expand the answer using only grounded source text.\n"
            "- If it is a new meaning, create a new stable topic-like title.\n"
            "- Do not output standalone generated questions as entries.\n"
        )
        return (
            f"{instruction}\n\n"
            f"{carryover_instruction}\n"
            "STRICT OUTPUT CONTRACT:\n"
            "- Return exactly one JSON object matching the requested schema.\n"
            "- Do not return markdown fences.\n"
            "- Do not return explanations before or after JSON.\n"
            "- Do not return multiple JSON objects.\n"
            "- Keep entries compact because this is one small technical source slice.\n"
            "NOW PROCESS THIS SOURCE JSON. Return ONLY the JSON result:\n"
            f"{json.dumps(source_payload, ensure_ascii=False)}"
        )


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
    prompt_file = MODE_PROMPT_FILES.get(mode)
    if not prompt_file:
        raise KnowledgePreprocessingValidationError(f"No prompt for mode: {mode}")

    path = PROMPTS_DIR / prompt_file
    return path.read_text(encoding="utf-8")


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
