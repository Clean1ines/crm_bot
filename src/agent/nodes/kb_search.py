"""
Knowledge base search node for LangGraph pipeline.

Performs semantic search using the search_knowledge tool and stores results in state.
"""

from typing import Dict, Any

from src.core.logging import get_logger
from src.agent.state import AgentState
from src.tools.registry import ToolRegistry

logger = get_logger(__name__)


def create_kb_search_node(tool_registry: ToolRegistry):
    """
    Factory function that creates a kb_search node with injected ToolRegistry.

    Args:
        tool_registry: ToolRegistry instance for executing search_knowledge.

    Returns:
        An async function that takes an AgentState dict and returns a dict
        with updated knowledge_chunks.
    """
    async def kb_search_node(state: AgentState) -> Dict[str, Any]:
        """
        Execute knowledge base search and store results in state.

        Expected state fields:
          - project_id: str
          - user_input: str
          - (optional) history, summary etc. – not used directly.

        Returns a dict with updates to the state:
          - knowledge_chunks: list of search results with 'answer' and 'score'.
        """
        project_id = state.get("project_id")
        query = state.get("user_input", "")

        if not project_id or not query:
            logger.warning("kb_search_node called without project_id or query")
            return {"knowledge_chunks": []}

        logger.info("KB search started", extra={"project_id": project_id, "query": query[:100]})

        try:
            # project_id передаётся через context, не в args
            result = await tool_registry.execute(
                "search_knowledge",
                {
                    "query": query,
                    "limit": 10  # increased from 5 to improve recall
                },
                context={"project_id": project_id}
            )
            # result is expected to be {"results": [...]}
            chunks = result.get("results", [])
            logger.info("KB search returned %d chunks", len(chunks), extra={"project_id": project_id})
            if chunks:
                for i, chunk in enumerate(chunks):
                    logger.debug("Result %d: score=%.3f, answer=%s", i+1, chunk.get("score", 0), chunk.get("answer", "")[:50])
            else:
                logger.warning("KB search returned no results", extra={"project_id": project_id, "query": query[:100]})
            return {"knowledge_chunks": chunks}
        except Exception as e:
            logger.exception("KB search failed", extra={"project_id": project_id, "error": str(e)})
            return {"knowledge_chunks": []}

    return kb_search_node
