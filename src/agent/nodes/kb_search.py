"""
Knowledge-search node for the LangGraph pipeline.

Performs project-scoped knowledge retrieval through the tool registry and
stores normalized chunks in graph state.
"""

import os
from collections.abc import Mapping
from typing import cast

from src.agent.state import AgentState
from src.domain.runtime.knowledge_search import (
    KnowledgeChunk,
    KnowledgeSearchContext,
    KnowledgeSearchResult,
)
from src.domain.runtime.state_contracts import RuntimeStateInput
from src.domain.runtime.tool_execution import ToolSafeErrorCode, ToolExecutionStatus
from src.infrastructure.logging.logger import get_logger, log_node_execution
from src.tools.registry import ToolRegistry

logger = get_logger(__name__)


def _rag_debug_enabled() -> bool:
    return os.getenv("RAG_DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}


def _preview_text(value: object, limit: int = 160) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    if not text:
        return None
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _chunk_trace_payload(chunk: KnowledgeChunk, rank: int) -> dict[str, object]:
    payload: dict[str, object] = {
        "rank": rank,
        "id": chunk.chunk_id,
        "score": chunk.score,
        "method": chunk.method,
        "entry_kind": chunk.entry_kind,
        "title": chunk.title,
        "source": chunk.source or chunk.document_id,
        "text_preview": _preview_text(chunk.content),
    }
    source_excerpt = _preview_text(chunk.source_excerpt)
    if source_excerpt:
        payload["source_excerpt_preview"] = source_excerpt
    if chunk.questions is not None:
        payload["questions_preview"] = _preview_text(chunk.questions)
    return {key: value for key, value in payload.items() if value is not None}


def _knowledge_search_exception_code(exc: BaseException) -> str:
    if isinstance(exc, TimeoutError):
        return ToolSafeErrorCode.TOOL_TIMEOUT.value
    if isinstance(exc, (ConnectionError, OSError)):
        return ToolSafeErrorCode.TOOL_UNAVAILABLE.value
    return ToolSafeErrorCode.KNOWLEDGE_SEARCH_FAILED.value


def create_kb_search_node(tool_registry: ToolRegistry):
    """
    Create the knowledge-search node with an injected tool registry.
    """

    async def _kb_search_node_impl(state: AgentState) -> dict[str, object]:
        context = KnowledgeSearchContext.from_state(cast(RuntimeStateInput, state))
        if not context.project_id or not context.query:
            logger.warning(
                "KB search skipped",
                extra={"project_id": context.project_id, "query": context.query},
            )
            patch = KnowledgeSearchResult().to_state_patch()
            patch["knowledge_retrieval_status"] = "skipped"
            return dict(patch)

        logger.info(
            "KB search start",
            extra={
                "project_id": context.project_id,
                "query_hash": context.query_hash,
                "query_len": len(context.query),
                "original_user_input_hash": context.original_user_input_hash,
                "original_user_input_len": len(context.original_user_input),
            },
        )

        try:
            payload = await tool_registry.execute(
                "search_knowledge",
                {"query": context.query, "limit": 10},
                context={
                    "project_id": context.project_id,
                    "thread_id": context.thread_id,
                },
            )
            if payload.status is not ToolExecutionStatus.SUCCEEDED:
                logger.error(
                    "KB search tool returned non-success outcome",
                    extra={
                        "project_id": context.project_id,
                        "tool_execution_status": payload.status.value,
                        "safe_error_code": payload.safe_error_code,
                    },
                )
                patch = KnowledgeSearchResult().to_state_patch()
                patch["knowledge_retrieval_status"] = "failed"
                patch["knowledge_retrieval_error_type"] = (
                    payload.safe_error_code or "knowledge_search_failed"
                )
                return dict(patch)

            if not isinstance(payload.payload, Mapping):
                logger.error(
                    "KB search tool returned malformed success payload",
                    extra={
                        "project_id": context.project_id,
                        "payload_type": type(payload.payload).__name__,
                    },
                )
                patch = KnowledgeSearchResult().to_state_patch()
                patch["knowledge_retrieval_status"] = "failed"
                patch["knowledge_retrieval_error_type"] = "invalid_tool_outcome"
                return dict(patch)

            result = KnowledgeSearchResult.from_tool_payload(payload.payload)

            logger.info(
                "KB search result",
                extra={
                    "project_id": context.project_id,
                    "query_hash": context.query_hash,
                    "chunks_count": len(result.chunks),
                    "chunk_ids": result.ids(),
                    "scores": result.scores(),
                },
            )
            if _rag_debug_enabled():
                logger.info(
                    "RAG semantic retrieval trace",
                    extra={
                        "project_id": context.project_id,
                        "thread_id": context.thread_id,
                        "original_user_input_hash": context.original_user_input_hash,
                        "original_user_input_len": len(context.original_user_input),
                        "resolved_query_hash": context.query_hash,
                        "resolved_query_len": len(context.query),
                        "resolved_query_preview": _preview_text(context.query),
                        "turn_relation": state.get("turn_relation"),
                        "topic": state.get("topic"),
                        "cta": state.get("cta"),
                        "entries_count": len(result.chunks),
                        "top_entries": [
                            _chunk_trace_payload(chunk, rank)
                            for rank, chunk in enumerate(result.chunks[:5], start=1)
                        ],
                    },
                )
            logger.info(
                "KB order signature",
                extra={
                    "query_hash": context.query_hash,
                    "order": "|".join(result.ids()),
                },
            )

            if not result.chunks:
                logger.warning(
                    "KB empty result",
                    extra={
                        "project_id": context.project_id,
                        "query_hash": context.query_hash,
                        "query_len": len(context.query),
                        "query_preview": _preview_text(context.query),
                    },
                )

            if len(set(result.ids())) != len(result.ids()):
                logger.error(
                    "KB duplicate ids detected", extra={"chunk_ids": result.ids()}
                )

            if result.chunks and any(score is None for score in result.scores()):
                logger.warning(
                    "KB missing scores detected",
                    extra={"chunk_scores": result.scores()},
                )

            patch = result.to_state_patch()
            return dict(patch)
        except Exception as exc:
            logger.exception(
                "KB search failed",
                extra={
                    "project_id": context.project_id,
                    "query_hash": context.query_hash,
                    "query_len": len(context.query),
                    "query_preview": _preview_text(context.query),
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
            )
            patch = KnowledgeSearchResult(
                retrieval_status="failed",
                error_type=_knowledge_search_exception_code(exc),
            ).to_state_patch()
            return dict(patch)

    def _get_kb_search_input_size(state: AgentState) -> int:
        return len(str(state.get("user_input") or ""))

    def _get_kb_search_output_size(result: dict[str, object]) -> int:
        chunks = result.get("knowledge_chunks")
        return len(chunks) if isinstance(chunks, list) else 0

    async def kb_search_node(state: AgentState) -> dict[str, object]:
        return await log_node_execution(
            "kb_search",
            _kb_search_node_impl,
            state,
            get_input_size=_get_kb_search_input_size,
            get_output_size=_get_kb_search_output_size,
        )

    return kb_search_node
