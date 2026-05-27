from __future__ import annotations

import hashlib
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
from src.domain.project_plane.json_types import JsonObject, json_value_from_unknown
from src.domain.project_plane.knowledge_preprocessing import (
    ANSWER_RESOLUTION_PROMPT_VERSION,
    MODE_FAQ,
    MODE_INSTRUCTION,
    MODE_PRICE_LIST,
    KnowledgeAnswerResolutionCase,
    KnowledgeAnswerResolutionResult,
    KnowledgeAnswerResolverExecutionResult,
    KnowledgePreprocessingEntry,
    KnowledgePreprocessingExecutionResult,
    KnowledgePreprocessingMode,
    KnowledgePreprocessingResult,
    KnowledgePreprocessingValidationError,
    parse_answer_resolution_payload,
    parse_preprocessing_payload,
    prompt_version_for_mode,
)
from src.domain.project_plane.knowledge_preprocessing_cleanup import (
    cleanup_faq_preprocessing_entries,
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
ANSWER_RESOLUTION_PROMPT_FILE = "knowledge_answer_resolution.txt"
SUPPORTED_PROMPT_LANGUAGES = {"ru", "en", "de", "es"}

GROQ_INSTANT_MODEL_ID = "llama-3.1-8b-instant"
GROQ_LARGE_REQUEST_FALLBACK_MODEL_ID = "meta-llama/llama-4-scout-17b-16e-instruct"
GROQ_INSTANT_FREE_TPM_LIMIT = 6000


def _estimate_groq_request_tokens(
    *,
    prompt: str,
    max_tokens: int,
) -> int:
    """Conservative local estimate for Groq TPM routing.

    Groq rejected the previous document batches because requested tokens
    exceeded llama-3.1-8b-instant Free TPM. We do not need exact tokenizer
    parity here; we need a safe preflight budget to route large requests to
    a model with a larger TPM limit.
    """

    estimated_input_tokens = max(
        1,
        (len(STRICT_JSON_SYSTEM_MESSAGE) + len(prompt) + 2) // 3,
    )
    return estimated_input_tokens + max_tokens


def _usage_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _dominant_case_language(cases: Sequence[KnowledgeAnswerResolutionCase]) -> str:
    counts: dict[str, int] = {}
    for case in cases:
        lang = case.expected_answer_language.strip().lower()
        if lang in SUPPORTED_PROMPT_LANGUAGES:
            counts[lang] = counts.get(lang, 0) + 1
    if not counts:
        return "unknown"
    sorted_counts = sorted(counts.items(), key=lambda item: item[1], reverse=True)
    if len(sorted_counts) > 1 and sorted_counts[0][1] == sorted_counts[1][1]:
        return "unknown"
    return sorted_counts[0][0]


def _answer_resolution_prompt_file(language: str) -> str:
    normalized = language.strip().lower()
    if normalized in SUPPORTED_PROMPT_LANGUAGES:
        return f"knowledge_answer_resolution.{normalized}.txt"
    return ANSWER_RESOLUTION_PROMPT_FILE


def _cleanup_faq_preprocessing_result(
    result: KnowledgePreprocessingResult,
) -> KnowledgePreprocessingResult:
    if result.mode != MODE_FAQ:
        return result

    cleanup = cleanup_faq_preprocessing_entries(result.entries)
    if not cleanup.metrics:
        return result

    return KnowledgePreprocessingResult(
        mode=result.mode,
        prompt_version=result.prompt_version,
        model=result.model,
        entries=cleanup.entries,
        metrics={
            **result.metrics,
            "faq_post_merge_cleanup": {
                str(key): json_value_from_unknown(value)
                for key, value in cleanup.metrics.items()
            },
        },
    )


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

    def _model_for_json_request(
        self,
        *,
        task: str,
        prompt: str,
        max_tokens: int,
    ) -> str:
        estimated_request_tokens = _estimate_groq_request_tokens(
            prompt=prompt,
            max_tokens=max_tokens,
        )
        if (
            self._model == GROQ_INSTANT_MODEL_ID
            and estimated_request_tokens > GROQ_INSTANT_FREE_TPM_LIMIT
        ):
            logger.warning(
                "Groq request exceeds selected model TPM; using fallback model for this call",
                extra={
                    "task": task,
                    "selected_model": self._model,
                    "fallback_model": GROQ_LARGE_REQUEST_FALLBACK_MODEL_ID,
                    "estimated_request_tokens": estimated_request_tokens,
                    "selected_model_tpm_limit": GROQ_INSTANT_FREE_TPM_LIMIT,
                },
            )
            return GROQ_LARGE_REQUEST_FALLBACK_MODEL_ID

        return self._model

    async def preprocess(
        self,
        *,
        mode: KnowledgePreprocessingMode,
        chunks: list[JsonObject],
        file_name: str,
    ) -> KnowledgePreprocessingExecutionResult:
        prompt_version = prompt_version_for_mode(mode)
        prompt = self._build_prompt(
            mode=mode,
            chunks=chunks,
            file_name=file_name,
        )

        max_tokens = 4000
        request_model = self._model_for_json_request(
            task="preprocess",
            prompt=prompt,
            max_tokens=max_tokens,
        )

        try:
            response = await self._client.chat.completions.create(
                model=request_model,
                messages=[
                    {"role": "system", "content": STRICT_JSON_SYSTEM_MESSAGE},
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content or ""
            _log_llm_response(
                task="preprocess",
                mode=mode,
                model=request_model,
                prompt_version=prompt_version,
                content=content,
                response=response,
            )
            result = parse_preprocessing_payload(
                content, mode=mode, model=request_model, prompt_version=prompt_version
            )
            result = _cleanup_faq_preprocessing_result(result)
            return KnowledgePreprocessingExecutionResult(
                result=result,
                usage=_response_usage_measurement(
                    response=response,
                    model=request_model,
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

    async def resolve_answer_cases(
        self,
        *,
        mode: KnowledgePreprocessingMode,
        file_name: str,
        cases: Sequence[KnowledgeAnswerResolutionCase],
        existing_project_titles: Sequence[str] = (),
    ) -> KnowledgeAnswerResolverExecutionResult:
        prompt_version = ANSWER_RESOLUTION_PROMPT_VERSION

        if not cases:
            return KnowledgeAnswerResolverExecutionResult(
                result=KnowledgeAnswerResolutionResult(
                    mode=mode,
                    prompt_version=prompt_version,
                    model=self._model,
                    decisions=(),
                    metrics={"group_count": 0},
                ),
                usage=None,
            )

        prompt_language = _dominant_case_language(cases)
        prompt = self._build_answer_resolution_prompt(
            mode=mode,
            file_name=file_name,
            cases=cases,
            existing_project_titles=existing_project_titles,
            language=prompt_language,
        )

        max_tokens = 3000
        request_model = self._model_for_json_request(
            task="answer_resolution",
            prompt=prompt,
            max_tokens=max_tokens,
        )

        try:
            response = await self._client.chat.completions.create(
                model=request_model,
                messages=[
                    {"role": "system", "content": STRICT_JSON_SYSTEM_MESSAGE},
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content or ""
            _log_llm_response(
                task="answer_resolution",
                mode=mode,
                model=request_model,
                prompt_version=prompt_version,
                content=content,
                response=response,
            )
            result = parse_answer_resolution_payload(
                content,
                mode=mode,
                model=request_model,
                prompt_version=prompt_version,
            )
            return KnowledgeAnswerResolverExecutionResult(
                result=result,
                usage=_response_usage_measurement(
                    response=response,
                    model=request_model,
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
                "Knowledge answer resolution failed",
                extra={
                    "mode": mode,
                    "model": self._model,
                    "group_count": len(cases),
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:300],
                },
            )
            raise

    def _build_answer_resolution_prompt(
        self,
        *,
        mode: KnowledgePreprocessingMode,
        file_name: str,
        cases: Sequence[KnowledgeAnswerResolutionCase],
        existing_project_titles: Sequence[str] = (),
        language: str = "unknown",
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
            "cases": [case.to_payload() for case in cases],
        }

        instruction = _load_answer_resolution_prompt(
            _answer_resolution_prompt_file(language)
        )
        return f"{instruction}{json.dumps(merge_payload, ensure_ascii=False)}"

    def _build_prompt(
        self,
        *,
        mode: KnowledgePreprocessingMode,
        chunks: list[JsonObject],
        file_name: str,
    ) -> str:
        instruction = _load_mode_prompt(mode)
        source_payload = {
            "file_name": file_name,
            "mode": mode,
            "chunks": [
                _structured_source_chunk_payload(
                    chunk=chunk,
                    index=_source_payload_index(chunk, fallback=index),
                    max_content_chars=self._max_chunk_chars,
                )
                for index, chunk in enumerate(chunks[: self._max_chunks])
            ],
        }
        return f"{instruction}\n{json.dumps(source_payload, ensure_ascii=False)}"


def _truncated_text(value: object, *, max_chars: int) -> str:
    text = str(value or "").strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip()


def _structured_child_payload(value: object, *, max_chars: int) -> JsonObject:
    if not isinstance(value, dict):
        return {}

    payload: JsonObject = {}
    for key in ("title", "body", "source_excerpt"):
        if key in value:
            payload[key] = _truncated_text(value.get(key), max_chars=max_chars)
    for key in ("section_path", "start_offset", "end_offset"):
        if key in value:
            payload[key] = json_value_from_unknown(value.get(key))
    return payload


def _source_payload_index(chunk: JsonObject, *, fallback: int) -> int:
    raw_index = chunk.get("index")
    if (
        isinstance(raw_index, int)
        and not isinstance(raw_index, bool)
        and raw_index >= 0
    ):
        return raw_index
    return fallback


def _structured_source_chunk_payload(
    *,
    chunk: JsonObject,
    index: int,
    max_content_chars: int,
) -> JsonObject:
    is_markdown_semantic = bool(chunk.get("section_body") or chunk.get("children"))
    section_max_chars = (
        max_content_chars
        if not is_markdown_semantic
        else max(
            max_content_chars,
            12000,
        )
    )
    payload: JsonObject = {
        "index": index,
        "content": _truncated_text(
            chunk.get("content"),
            max_chars=section_max_chars,
        ),
    }
    passthrough_keys = (
        "id",
        "source_format",
        "semantic_unit_id",
        "semantic_unit_role_hint",
        "section_title",
        "section_body",
        "section_path",
        "source_excerpt",
        "source_refs",
        "start_offset",
        "end_offset",
    )
    for key in passthrough_keys:
        if key not in chunk:
            continue

        value = chunk[key]
        if key in {"section_body", "source_excerpt"}:
            payload[key] = _truncated_text(value, max_chars=section_max_chars)
        else:
            payload[key] = json_value_from_unknown(value)

    children = chunk.get("children")
    if isinstance(children, list):
        child_payloads: list[JsonObject] = []
        for child in children[:12]:
            child_payload = _structured_child_payload(
                child,
                max_chars=max(600, section_max_chars),
            )
            if child_payload:
                child_payloads.append(child_payload)
        payload["children"] = json_value_from_unknown(child_payloads)

    return payload


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

    response_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    chunk_count = max(
        1,
        (len(content) + KCD_LLM_RESPONSE_LOG_CHUNK_CHARS - 1)
        // KCD_LLM_RESPONSE_LOG_CHUNK_CHARS,
    )
    logger.info(
        "Knowledge LLM JSON response received",
        extra={
            **base_extra,
            "response_sha256": response_hash,
            "response_chunk_count": chunk_count,
        },
    )


def _load_mode_prompt(mode: KnowledgePreprocessingMode) -> str:
    if mode not in {MODE_FAQ, MODE_PRICE_LIST, MODE_INSTRUCTION}:
        raise KnowledgePreprocessingValidationError(
            f"Knowledge answer compiler is unavailable for mode: {mode}"
        )
    return (PROMPTS_DIR / FAQ_COMPILER_PROMPT_FILE).read_text(encoding="utf-8")


def _load_answer_resolution_prompt(
    file_name: str = ANSWER_RESOLUTION_PROMPT_FILE,
) -> str:
    return (PROMPTS_DIR / file_name).read_text(encoding="utf-8")


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
