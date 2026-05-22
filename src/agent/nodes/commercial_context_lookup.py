from __future__ import annotations

from typing import cast

from src.agent.state import AgentState
from src.domain.runtime.commercial_context import (
    CommercialContextLookupContext,
    CommercialContextLookupResult,
)
from src.domain.runtime.state_contracts import RuntimeStateInput
from src.infrastructure.logging.logger import get_logger, log_node_execution
from src.tools.registry import ToolRegistry


logger = get_logger(__name__)


def create_commercial_context_lookup_node(tool_registry: ToolRegistry):
    """Create a pre-RAG structured commercial context lookup node."""

    async def _commercial_context_lookup_node_impl(
        state: AgentState,
    ) -> dict[str, object]:
        context = CommercialContextLookupContext.from_state(
            cast(RuntimeStateInput, state)
        )
        if not context.project_id or not context.query:
            logger.debug(
                "Commercial context lookup skipped",
                extra={"project_id": context.project_id, "query": context.query},
            )
            return dict(
                CommercialContextLookupResult.skipped(
                    "missing_project_or_query"
                ).to_state_patch()
            )

        logger.info(
            "Commercial context lookup start",
            extra={
                "project_id": context.project_id,
                "thread_id": context.thread_id,
                "query_hash": context.query_hash,
            },
        )

        try:
            payload = await tool_registry.execute(
                "commercial_price_lookup",
                {
                    "item_name": context.query,
                    "limit": 5,
                },
                context={
                    "project_id": context.project_id,
                    "thread_id": context.thread_id,
                },
            )
            result = CommercialContextLookupResult.from_tool_payload(payload)
            logger.info(
                "Commercial context lookup result",
                extra={
                    "project_id": context.project_id,
                    "query_hash": context.query_hash,
                    "status": result.status,
                    "source_count": len(result.sources),
                },
            )
            return dict(result.to_state_patch())
        except Exception as exc:
            logger.exception(
                "Commercial context lookup failed",
                extra={
                    "project_id": context.project_id,
                    "query_hash": context.query_hash,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "policy": "degrade_to_kb_search",
                },
            )
            return dict(
                CommercialContextLookupResult.error(
                    "tool_execution_failed"
                ).to_state_patch()
            )

    def _get_commercial_context_input_size(state: AgentState) -> int:
        return len(str(state.get("user_input") or ""))

    def _get_commercial_context_output_size(result: dict[str, object]) -> int:
        return len(str(result.get("commercial_context") or ""))

    async def commercial_context_lookup_node(state: AgentState) -> dict[str, object]:
        return await log_node_execution(
            "commercial_context_lookup",
            _commercial_context_lookup_node_impl,
            state,
            get_input_size=_get_commercial_context_input_size,
            get_output_size=_get_commercial_context_output_size,
        )

    return commercial_context_lookup_node
