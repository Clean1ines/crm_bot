from __future__ import annotations

import asyncio
import json
import os
import re
import time
from collections.abc import Mapping
from pathlib import Path

from groq import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AsyncGroq,
    RateLimitError,
)

from src.application.ports.knowledge.runtime_search import (
    KnowledgeRuntimeRetrievalPort,
)
from src.application.rag_eval.ports import RagEvalSearchWithExpansionPort
from src.application.rag_eval.schemas import JsonObject, RagEvalEvidenceEntry
from src.domain.project_plane.knowledge_views import (
    KnowledgeSearchResultView,
    SourceRefView,
    source_refs_from_excerpt,
)
from src.infrastructure.config.settings import settings
from src.infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


_RAG_EVAL_LLM_LOCK = asyncio.Lock()
_RAG_EVAL_LAST_CALL_MONOTONIC = 0.0


def _default_async_groq_client() -> AsyncGroq:
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if api_key:
        return AsyncGroq(api_key=api_key)
    return AsyncGroq()


def _rag_eval_llm_min_delay_seconds() -> float:
    raw = os.getenv("RAG_EVAL_LLM_MIN_DELAY_SECONDS", "0").strip()
    try:
        value = float(raw)
    except ValueError:
        return 20.0
    return max(0.0, value)


async def _throttle_rag_eval_llm_call() -> None:
    """Optionally pace RAG-eval LLM calls per process to reduce Groq TPM 429s.

    This throttle is intentionally local to the RAG-eval JSON adapter. It does
    not affect the production chatbot response generator.
    """

    global _RAG_EVAL_LAST_CALL_MONOTONIC

    min_delay = _rag_eval_llm_min_delay_seconds()
    if min_delay <= 0:
        return

    async with _RAG_EVAL_LLM_LOCK:
        now = time.monotonic()
        elapsed = now - _RAG_EVAL_LAST_CALL_MONOTONIC
        if _RAG_EVAL_LAST_CALL_MONOTONIC > 0 and elapsed < min_delay:
            await asyncio.sleep(min_delay - elapsed)
        _RAG_EVAL_LAST_CALL_MONOTONIC = time.monotonic()


def _usage_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return max(0, value)


class GroqRagEvalJsonLlmAdapter:
    """Groq-backed JSON-only LLM adapter for RAG eval generation and judging."""

    def __init__(
        self,
        *,
        client: AsyncGroq | None = None,
        model: str | None = None,
        fallback_model: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> None:
        self._client = client or _default_async_groq_client()
        self._model = model or settings.GROQ_MODEL
        self._fallback_model = fallback_model.strip() if fallback_model else None
        if self._fallback_model == self._model:
            self._fallback_model = None
        self._temperature = temperature
        self._max_tokens = max(256, max_tokens)
        self._tokens_input = 0
        self._tokens_output = 0
        self._tokens_total = 0
        self._fallback_used_count = 0

    def usage_snapshot(self) -> JsonObject:
        return {
            "tokens_input": self._tokens_input,
            "tokens_output": self._tokens_output,
            "tokens_total": self._tokens_total,
            "fallback_used_count": self._fallback_used_count,
        }

    async def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
    ) -> Mapping[str, object]:
        try:
            return await self._complete_json_with_model(
                model=self._model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                schema_name=schema_name,
                is_fallback=False,
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
            json.JSONDecodeError,
        ) as primary_exc:
            if not self._fallback_model:
                raise

            logger.warning(
                "RAG eval primary JSON LLM failed; trying fallback model",
                extra={
                    "schema_name": schema_name,
                    "primary_model": self._model,
                    "fallback_model": self._fallback_model,
                    "error_type": type(primary_exc).__name__,
                    "error": str(primary_exc)[:300],
                },
            )
            return await self._complete_json_with_model(
                model=self._fallback_model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                schema_name=schema_name,
                is_fallback=True,
            )

    async def _complete_json_with_model(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
        is_fallback: bool,
    ) -> Mapping[str, object]:
        try:
            await _throttle_rag_eval_llm_call()
            response = await self._client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=self._temperature,
                max_tokens=self._max_tokens,
            )
            content = str(response.choices[0].message.content or "")
            self._record_usage(
                response=response,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                content=content,
            )
            payload = _extract_json_object(content)
            if not isinstance(payload, Mapping):
                raise ValueError(f"{schema_name} response is not a JSON object")
            if is_fallback:
                self._fallback_used_count += 1
            return payload
        except (
            APIConnectionError,
            APIError,
            APITimeoutError,
            RateLimitError,
            AttributeError,
            IndexError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ) as exc:
            logger.warning(
                "RAG eval JSON LLM call failed",
                extra={
                    "schema_name": schema_name,
                    "model": model,
                    "is_fallback": is_fallback,
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:300],
                },
            )
            raise

    def _record_usage(
        self,
        *,
        response: object,
        system_prompt: str,
        user_prompt: str,
        content: str,
    ) -> None:
        usage = getattr(response, "usage", None)
        prompt_tokens = _usage_int(getattr(usage, "prompt_tokens", None))
        completion_tokens = _usage_int(getattr(usage, "completion_tokens", None))
        total_tokens = _usage_int(getattr(usage, "total_tokens", None))

        if prompt_tokens is None:
            prompt_tokens = max(1, (len(system_prompt) + len(user_prompt) + 3) // 4)
        if completion_tokens is None:
            completion_tokens = max(1, (len(content) + 3) // 4)
        if total_tokens is None:
            total_tokens = prompt_tokens + completion_tokens

        self._tokens_input += prompt_tokens
        self._tokens_output += completion_tokens
        self._tokens_total += total_tokens


class FallbackRagEvalJsonLlmAdapter:
    """JSON LLM adapter that uses fallback only after primary failure.

    The primary model is tried first. A small primary retry protects against
    transient provider/JSON failures. The fallback model is used only when the
    primary still cannot return a valid compact JSON object.
    """

    def __init__(
        self,
        *,
        primary_model: str,
        fallback_model: str | None,
        temperature: float = 0.1,
        max_tokens: int = 2048,
        primary_attempts: int = 2,
    ) -> None:
        self._primary = GroqRagEvalJsonLlmAdapter(
            model=primary_model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        self._fallback = (
            GroqRagEvalJsonLlmAdapter(
                model=fallback_model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            if fallback_model
            else None
        )
        self._primary_attempts = max(1, min(3, primary_attempts))
        self._fallback_used_count = 0
        self._primary_retry_count = 0

    def usage_snapshot(self) -> JsonObject:
        primary = self._primary.usage_snapshot()
        fallback = self._fallback.usage_snapshot() if self._fallback is not None else {}
        primary_input = _usage_int(primary.get("tokens_input")) or 0
        primary_output = _usage_int(primary.get("tokens_output")) or 0
        primary_total = _usage_int(primary.get("tokens_total")) or 0
        fallback_input = _usage_int(fallback.get("tokens_input")) or 0
        fallback_output = _usage_int(fallback.get("tokens_output")) or 0
        fallback_total = _usage_int(fallback.get("tokens_total")) or 0
        return {
            "tokens_input": primary_input + fallback_input,
            "tokens_output": primary_output + fallback_output,
            "tokens_total": primary_total + fallback_total,
            "fallback_used_count": self._fallback_used_count,
            "adapter_retry_count": self._primary_retry_count,
        }

    async def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
    ) -> Mapping[str, object]:
        primary_error: BaseException | None = None
        for attempt in range(1, self._primary_attempts + 1):
            try:
                return await self._primary.complete_json(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    schema_name=schema_name,
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
                json.JSONDecodeError,
            ) as exc:
                primary_error = exc
                if attempt < self._primary_attempts:
                    self._primary_retry_count += 1
                    continue

        if self._fallback is None:
            if primary_error is not None:
                raise primary_error
            raise ValueError(f"{schema_name} primary model failed without an exception")

        self._fallback_used_count += 1
        logger.warning(
            "RAG eval question model fallback used",
            extra={
                "schema_name": schema_name,
                "primary_error_type": type(primary_error).__name__
                if primary_error
                else "unknown",
                "primary_error": str(primary_error)[:300] if primary_error else "",
            },
        )
        try:
            return await self._fallback.complete_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                schema_name=schema_name,
            )
        except Exception as fallback_error:
            if primary_error is not None:
                raise fallback_error from primary_error
            raise


class RagServiceRagEvalRetriever:
    """RagEval retriever adapter over the production RAGService."""

    def __init__(self, rag_service: RagEvalSearchWithExpansionPort) -> None:
        self._rag_service = rag_service

    async def retrieve(
        self,
        *,
        project_id: str,
        question: str,
        limit: int,
    ) -> list[RagEvalEvidenceEntry]:
        rows = await self._rag_service.search_with_expansion(
            project_id=project_id,
            query=question,
            final_limit=limit,
        )

        chunks: list[RagEvalEvidenceEntry] = []
        for index, row in enumerate(rows):
            chunk = _entry_from_mapping(row, fallback_id=f"retrieved_{index}")
            if chunk is not None:
                chunks.append(chunk)

        return chunks


class VectorOnlyRagEvalRetriever:
    """Diagnostic vector-only RAG eval retriever.

    This calls the production-safe repository surface with hybrid_fallback=False,
    so it uses RUNTIME_VECTOR_SEARCH_SQL and avoids lexical/hybrid ranking,
    query expansion, and RAGService rerank side effects.
    """

    def __init__(self, retrieval: KnowledgeRuntimeRetrievalPort) -> None:
        self._retrieval = retrieval

    async def retrieve(
        self,
        *,
        project_id: str,
        question: str,
        limit: int,
    ) -> list[RagEvalEvidenceEntry]:
        rows = await self._retrieval.search(
            project_id=project_id,
            query=question,
            limit=limit,
            hybrid_fallback=False,
            thread_id=None,
        )
        return [_entry_from_knowledge_view(row) for row in rows]


class LocalRagEvalReportSink:
    """Writes human-readable RAG eval reports under reports/."""

    def __init__(self, *, reports_dir: str | Path = "reports") -> None:
        self._reports_dir = Path(reports_dir)

    async def write_json_report(
        self,
        *,
        run_id: str,
        payload: JsonObject,
    ) -> None:
        self._reports_dir.mkdir(parents=True, exist_ok=True)
        path = self._reports_dir / f"rag-eval-{run_id}.json"
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

    async def write_markdown_report(
        self,
        *,
        run_id: str,
        markdown: str,
    ) -> None:
        self._reports_dir.mkdir(parents=True, exist_ok=True)
        path = self._reports_dir / f"rag-eval-{run_id}.md"
        path.write_text(markdown, encoding="utf-8")


def _extract_json_object(content: str) -> Mapping[str, object]:
    text = _strip_json_fence(content.strip())
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise
        payload = json.loads(match.group(0))

    if not isinstance(payload, Mapping):
        raise ValueError("JSON payload is not an object")
    return payload


def _strip_json_fence(text: str) -> str:
    if not text.startswith("```"):
        return text

    stripped = text.strip("`").strip()
    if stripped.startswith("json"):
        return stripped[4:].strip()
    return stripped


def _entry_from_knowledge_view(row: KnowledgeSearchResultView) -> RagEvalEvidenceEntry:
    return RagEvalEvidenceEntry(
        id=row.id,
        content=row.content,
        document_id=row.document_id,
        source=row.source,
        score=row.score,
        source_refs=row.source_refs,
        metadata={
            "score": row.score,
            "method": row.method,
            "title": row.title,
            "document_status": row.document_status,
            "entry_kind": row.entry_kind,
            "source_excerpt": row.source_excerpt,
            "source_refs": [source_ref.to_dict() for source_ref in row.source_refs],
            "questions": row.questions,
            "synonyms": row.synonyms,
            "tags": row.tags,
        },
    )


def _entry_from_mapping(
    row: Mapping[str, object],
    *,
    fallback_id: str,
) -> RagEvalEvidenceEntry | None:
    content = str(row.get("content") or row.get("text") or "").strip()
    if not content:
        return None

    entry_id = str(row.get("id") or row.get("entry_id") or fallback_id)
    source_refs = _source_refs_from_mapping(row)
    return RagEvalEvidenceEntry(
        id=entry_id,
        content=content,
        document_id=_optional_text(row.get("document_id")),
        source=_optional_text(row.get("source")),
        source_refs=source_refs,
        metadata={
            "score": row.get("score"),
            "method": row.get("method"),
            "title": row.get("title"),
            "chunk_index": row.get("chunk_index"),
            "document_status": row.get("document_status"),
            "entry_kind": row.get("entry_kind"),
            "source_excerpt": row.get("source_excerpt"),
            "source_refs": [source_ref.to_dict() for source_ref in source_refs],
            "questions": row.get("questions"),
            "synonyms": row.get("synonyms"),
            "tags": row.get("tags"),
        },
    )


def _source_refs_from_mapping(row: Mapping[str, object]) -> tuple[SourceRefView, ...]:
    raw_source_refs = row.get("source_refs")
    if isinstance(raw_source_refs, tuple) and all(
        isinstance(item, SourceRefView) for item in raw_source_refs
    ):
        return raw_source_refs
    return source_refs_from_excerpt(_optional_text(row.get("source_excerpt")))


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _prompt_entry(chunk: RagEvalEvidenceEntry) -> dict[str, object]:
    return {
        "id": chunk.id,
        "entry_id": chunk.id,
        "content": chunk.content,
        "text": chunk.content,
        "source": chunk.source,
        "document_id": chunk.document_id,
        "score": chunk.metadata.get("score"),
        "source_refs": [source_ref.to_dict() for source_ref in chunk.source_refs],
        "metadata": chunk.metadata,
    }
