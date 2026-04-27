"""
Knowledge-search node for the LangGraph pipeline.

Performs project-scoped knowledge retrieval through the tool registry and
stores normalized chunks in graph state.
"""


from src.agent.state import AgentState
from src.domain.runtime.knowledge_search import KnowledgeSearchContext, KnowledgeSearchResult
from src.infrastructure.logging.logger import get_logger, log_node_execution
from src.tools.registry import ToolRegistry

logger = get_logger(__name__)


def create_kb_search_node(tool_registry: ToolRegistry):
    """
    Create the knowledge-search node with an injected tool registry.
    """

    async def _kb_search_node_impl(state: AgentState) -> dict[str, object]:
        context = KnowledgeSearchContext.from_state(state)
        if not context.project_id or not context.query:
            logger.warning(
                "KB search skipped",
                extra={"project_id": context.project_id, "query": context.query},
            )
            return KnowledgeSearchResult().to_state_patch()

        logger.info(
            "KB search start",
            extra={
                "project_id": context.project_id,
                "query": context.query,
                "query_hash": context.query_hash,
                "query_len": len(context.query),
            },
        )

        try:
            payload = await tool_registry.execute(
                "search_knowledge",
                {"query": context.query, "limit": 10},
                context={"project_id": context.project_id},
            )
            result = KnowledgeSearchResult.from_tool_payload(payload)

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
                        "query": context.query,
                        "query_hash": context.query_hash,
                    },
                )

            if len(set(result.ids())) != len(result.ids()):
                logger.error("KB duplicate ids detected", extra={"chunk_ids": result.ids()})

            if result.chunks and any(score is None for score in result.scores()):
                logger.warning("KB missing scores detected", extra={"chunk_scores": result.scores()})

            return result.to_state_patch()
        except Exception as exc:
            logger.exception(
                "KB search failed",
                extra={
                    "project_id": context.project_id,
                    "query": context.query,
                    "error": str(exc),
                },
            )
            return KnowledgeSearchResult().to_state_patch()

    def _get_kb_search_input_size(state: AgentState) -> int:
        return len(str(state.get("user_input") or ""))

    def _get_kb_search_output_size(result: dict[str, object]) -> int:
        return len(result.get("knowledge_chunks", []))

    async def kb_search_node(state: AgentState) -> dict[str, object]:
        return await log_node_execution(
            "kb_search",
            _kb_search_node_impl,
            state,
            get_input_size=_get_kb_search_input_size,
            get_output_size=_get_kb_search_output_size,
        )

    return kb_search_node
