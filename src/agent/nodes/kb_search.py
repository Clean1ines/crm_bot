"""
Knowledge base search node for LangGraph pipeline.

Performs semantic search using the search_knowledge tool and stores results in state.
"""

from typing import Dict, Any, List
import hashlib

from src.core.logging import get_logger, log_node_execution
from src.agent.state import AgentState
from src.tools.registry import ToolRegistry

logger = get_logger(__name__)


def _hash_query(query: str) -> str:
    return hashlib.md5(query.encode("utf-8")).hexdigest()


def create_kb_search_node(tool_registry: ToolRegistry):

    async def _kb_search_node_impl(state: AgentState) -> Dict[str, Any]:

        project_id = state.get("project_id")
        query = state.get("user_input", "")

        if not project_id or not query:
            logger.warning(
                "KB SEARCH SKIPPED",
                extra={
                    "project_id": project_id,
                    "query": query
                }
            )
            return {"knowledge_chunks": []}

        query_hash = _hash_query(query)

        # =========================
        # TRACE INPUT
        # =========================
        logger.info(
            "KB SEARCH START",
            extra={
                "project_id": project_id,
                "query": query,
                "query_hash": query_hash,
                "query_len": len(query),
            }
        )

        try:

            # =========================
            # RETRIEVAL CALL (SINGLE SOURCE OF TRUTH)
            # =========================
            result = await tool_registry.execute(
                "search_knowledge",
                {
                    "query": query,
                    "limit": 10
                },
                context={"project_id": project_id}
            )

            chunks = result.get("results", [])

            # =========================
            # NORMALIZATION
            # =========================
            chunk_ids = []
            chunk_scores = []
            normalized_chunks = []

            for i, c in enumerate(chunks):
                chunk_id = c.get("id", f"no-id-{i}")
                score = c.get("score")

                chunk_ids.append(chunk_id)
                chunk_scores.append(score)

                normalized_chunks.append({
                    "id": chunk_id,
                    "score": score,
                    "content": (c.get("content") or "")[:150]   # <-- fix: use 'content' instead of 'answer'
                })

            # =========================
            # TRACE OUTPUT
            # =========================
            logger.info(
                "KB SEARCH RESULT",
                extra={
                    "project_id": project_id,
                    "query_hash": query_hash,
                    "chunks_count": len(chunks),
                    "chunk_ids": chunk_ids,
                    "scores": chunk_scores,
                }
            )

            # =========================
            # STABILITY DEBUG (CRITICAL)
            # =========================
            order_signature = "|".join(chunk_ids)

            logger.info(
                "KB ORDER SIGNATURE",
                extra={
                    "query_hash": query_hash,
                    "order": order_signature
                }
            )

            # =========================
            # ANOMALY DETECTION
            # =========================

            if len(chunks) == 0:
                logger.warning(
                    "KB EMPTY RESULT",
                    extra={
                        "project_id": project_id,
                        "query": query,
                        "query_hash": query_hash
                    }
                )

            if len(set(chunk_ids)) != len(chunk_ids):
                logger.error(
                    "KB DUPLICATE IDS DETECTED",
                    extra={
                        "chunk_ids": chunk_ids
                    }
                )

            if len(chunks) > 0 and any(s is None for s in chunk_scores):
                logger.warning(
                    "KB MISSING SCORES DETECTED",
                    extra={
                        "chunk_scores": chunk_scores
                    }
                )

            return {
                "knowledge_chunks": normalized_chunks
            }

        except Exception as e:
            logger.exception(
                "KB SEARCH FAILED",
                extra={
                    "project_id": project_id,
                    "query": query,
                    "error": str(e)
                }
            )
            return {"knowledge_chunks": []}

    def _get_kb_search_input_size(state: AgentState) -> int:
        return len(state.get("user_input", ""))

    def _get_kb_search_output_size(result: Dict[str, Any]) -> int:
        return len(result.get("knowledge_chunks", []))

    async def kb_search_node(state: AgentState) -> Dict[str, Any]:
        return await log_node_execution(
            "kb_search",
            _kb_search_node_impl,
            state,
            get_input_size=_get_kb_search_input_size,
            get_output_size=_get_kb_search_output_size
        )

    return kb_search_node
