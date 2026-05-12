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
    KnowledgePreprocessingEntry,
    KnowledgePreprocessingExecutionResult,
    KnowledgePreprocessingMode,
    entry_kind_for_preprocessing_mode,
    KnowledgePreprocessingValidationError,
    parse_preprocessing_payload,
    prompt_version_for_mode,
)
from src.domain.project_plane.model_usage_views import ModelUsageMeasurement
from src.infrastructure.config.settings import settings
from src.infrastructure.llm.groq_keyring import RotatingAsyncGroq
from src.infrastructure.logging.logger import get_logger

logger = get_logger(__name__)

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
        max_chunks: int = 30,
        max_chunk_chars: int = 1800,
    ) -> None:
        self._client = client or RotatingAsyncGroq()
        self._model = model or settings.GROQ_MODEL
        self._max_chunks = max(1, max_chunks)
        self._max_chunk_chars = max(200, max_chunk_chars)

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
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=4000,
            )
            content = response.choices[0].message.content or ""
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

    async def merge_answer_entry(
        self,
        *,
        mode: KnowledgePreprocessingMode,
        file_name: str,
        existing_entry: KnowledgePreprocessingEntry,
        incoming_entry: KnowledgePreprocessingEntry,
    ) -> KnowledgePreprocessingExecutionResult:
        prompt_version = prompt_version_for_mode(mode)
        prompt = self._build_merge_prompt(
            mode=mode,
            file_name=file_name,
            existing_entry=existing_entry,
            incoming_entry=incoming_entry,
        )

        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=2400,
            )
            content = response.choices[0].message.content or ""
            result = parse_preprocessing_payload(
                content,
                mode=mode,
                model=self._model,
                prompt_version=prompt_version,
            )
            if len(result.entries) != 1:
                raise KnowledgePreprocessingValidationError(
                    "Answer merge must return exactly one entry"
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
                "Knowledge answer merge failed",
                extra={
                    "mode": mode,
                    "model": self._model,
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:300],
                },
            )
            raise

    def _build_merge_prompt(
        self,
        *,
        mode: KnowledgePreprocessingMode,
        file_name: str,
        existing_entry: KnowledgePreprocessingEntry,
        incoming_entry: KnowledgePreprocessingEntry,
    ) -> str:
        instruction = _load_mode_prompt(mode)
        merge_payload = {
            "file_name": file_name,
            "mode": mode,
            "existing_entry": existing_entry.to_chunk(
                entry_kind=entry_kind_for_preprocessing_mode(mode)
            ),
            "incoming_entry": incoming_entry.to_chunk(
                entry_kind=entry_kind_for_preprocessing_mode(mode)
            ),
        }
        merge_instruction = (
            "ONE-MEANING MERGE TASK:\n"
            "- Merge exactly these two grounded answer entries into one "
            "canonical answer meaning.\n"
            "- Preserve only facts supported by existing_entry.source_excerpt "
            "or incoming_entry.source_excerpt.\n"
            "- Keep one stable topic-like title. Prefer existing_entry.title "
            "unless incoming_entry.title is clearly more precise.\n"
            "- Expand the answer when incoming_entry adds grounded details.\n"
            "- Merge questions, synonyms and tags as retrieval enrichment.\n"
            "- Return exactly one JSON entry in the same schema as the main "
            "preprocessing task.\n"
            "- Do not create standalone question/test/debug entries.\n"
        )
        return (
            f"{instruction}\n\n"
            f"{merge_instruction}\n"
            "NOW MERGE THIS JSON. Return ONLY the JSON result:\n"
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
            "NOW PROCESS THIS SOURCE JSON. Return ONLY the JSON result:\n"
            f"{json.dumps(source_payload, ensure_ascii=False)}"
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
