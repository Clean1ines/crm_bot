from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path

from groq import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AsyncGroq,
    RateLimitError,
)

from src.application.rag_eval.schemas import JsonObject, RagEvalChunk
from src.infrastructure.config.settings import settings
from src.infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


class GroqRagEvalJsonLlmAdapter:
    """Groq-backed JSON-only LLM adapter for RAG eval generation and judging."""

    def __init__(
        self,
        *,
        client: AsyncGroq | None = None,
        model: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> None:
        self._client = client or AsyncGroq(api_key=settings.GROQ_API_KEY)
        self._model = model or settings.GROQ_MODEL
        self._temperature = temperature
        self._max_tokens = max(256, max_tokens)

    async def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
    ) -> Mapping[str, object]:
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=self._temperature,
                max_tokens=self._max_tokens,
            )
            content = str(response.choices[0].message.content or "")
            payload = _extract_json_object(content)
            if not isinstance(payload, Mapping):
                raise ValueError(f"{schema_name} response is not a JSON object")
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
                    "model": self._model,
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:300],
                },
            )
            raise


class RagServiceRagEvalRetriever:
    """RagEval retriever adapter over the production RAGService."""

    def __init__(self, rag_service: object) -> None:
        self._rag_service = rag_service

    async def retrieve(
        self,
        *,
        project_id: str,
        question: str,
        limit: int,
    ) -> list[RagEvalChunk]:
        search = getattr(self._rag_service, "search_with_expansion")
        rows = await search(
            project_id=project_id,
            query=question,
            final_limit=limit,
        )
        if not isinstance(rows, list):
            return []

        chunks: list[RagEvalChunk] = []
        for index, row in enumerate(rows):
            if isinstance(row, Mapping):
                chunk = _chunk_from_mapping(row, fallback_id=f"retrieved_{index}")
                if chunk is not None:
                    chunks.append(chunk)

        return chunks


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


def _chunk_from_mapping(
    row: Mapping[str, object],
    *,
    fallback_id: str,
) -> RagEvalChunk | None:
    content = str(row.get("content") or row.get("text") or "").strip()
    if not content:
        return None

    chunk_id = str(row.get("id") or row.get("chunk_id") or fallback_id)
    return RagEvalChunk(
        id=chunk_id,
        content=content,
        document_id=_optional_text(row.get("document_id")),
        source=_optional_text(row.get("source")),
        metadata={
            "score": row.get("score"),
            "method": row.get("method"),
            "title": row.get("title"),
            "chunk_index": row.get("chunk_index"),
            "document_status": row.get("document_status"),
        },
    )


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _prompt_chunk(chunk: RagEvalChunk) -> dict[str, object]:
    return {
        "id": chunk.id,
        "chunk_id": chunk.id,
        "content": chunk.content,
        "text": chunk.content,
        "source": chunk.source,
        "document_id": chunk.document_id,
        "score": chunk.metadata.get("score"),
        "metadata": chunk.metadata,
    }
