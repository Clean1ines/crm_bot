"""
Load-state node for the LangGraph pipeline.

This node restores thread-scoped context such as history, summary, analytics,
and long-term memory before the rest of the graph executes.
"""

from typing import Any

from src.agent.state import AgentState
from src.domain.project_plane.thread_runtime import (
    ThreadAnalyticsSnapshot,
    ThreadRuntimeSnapshot,
)
from src.domain.runtime.load_state import LoadStateResult
from src.infrastructure.db.repositories.memory_repository import MemoryRepository
from src.infrastructure.logging.logger import get_logger, log_node_execution

logger = get_logger(__name__)


def create_load_state_node(thread_repo, project_repo, memory_repo: MemoryRepository | None = None):
    """
    Create the runtime load-state node with injected repository dependencies.

    Args:
        thread_repo: Repository used to load thread snapshots and history.
        project_repo: Reserved for future project-scoped enrichments.
        memory_repo: Optional repository for long-term user memory.

    Returns:
        Async LangGraph node that returns a state patch.
    """

    async def _load_state_node_impl(state: AgentState) -> dict[str, Any]:
        thread_id = state.get("thread_id")
        project_id = state.get("project_id")

        if not thread_id or not project_id:
            logger.error(
                "load_state_node called without thread_id or project_id",
                extra={"thread_id": thread_id, "project_id": project_id},
            )
            return {}

        logger.debug("Loading state", extra={"thread_id": thread_id, "project_id": project_id})

        thread_view = await thread_repo.get_thread_with_project_view(thread_id)
        thread_snapshot = ThreadRuntimeSnapshot.from_record(
            thread_view.to_record() if hasattr(thread_view, "to_record") else thread_view
        )
        if not thread_snapshot:
            logger.warning("Thread not found", extra={"thread_id": thread_id})
            return {}

        analytics_view = await thread_repo.get_analytics_view(thread_id)
        analytics = ThreadAnalyticsSnapshot.from_record(
            analytics_view.to_record() if analytics_view else None
        )
        analytics_patch = analytics.to_state_patch()
        if analytics_patch:
            logger.debug(
                "Loaded analytics",
                extra={"thread_id": thread_id, "analytics": analytics_patch},
            )

        recent_messages = await thread_repo.get_messages_for_langgraph(thread_id)
        if len(recent_messages) > 10:
            recent_messages = recent_messages[-10:]

        # Stored graph state is intentionally not restored yet. The new graph
        # uses explicit context loading instead of replaying arbitrary saved state.
        await thread_repo.get_state_json(thread_id)

        result = LoadStateResult(
            client_profile=None,
            conversation_summary=thread_snapshot.context_summary,
            history=recent_messages,
            knowledge_chunks=None,
            client_id=thread_snapshot.client_id,
            intent=analytics_patch.get("intent"),
            lifecycle=analytics_patch.get("lifecycle"),
            cta=analytics_patch.get("cta"),
            decision=analytics_patch.get("decision"),
        )

        if memory_repo and thread_snapshot.client_id:
            try:
                memory_views = await memory_repo.get_for_user_view(
                    project_id=project_id,
                    client_id=thread_snapshot.client_id,
                    limit=50,
                )
                memories = [
                    memory.to_record() if hasattr(memory, "to_record") else memory
                    for memory in memory_views
                ]
                result.user_memory = LoadStateResult.build_memory_index(memories)
                logger.debug(
                    "Loaded user memory",
                    extra={
                        "client_id": thread_snapshot.client_id,
                        "memory_count": len(memories),
                    },
                )

                if result.lifecycle is None:
                    lifecycle = await memory_repo.get_lifecycle(project_id, thread_snapshot.client_id)
                    if lifecycle:
                        result.lifecycle = lifecycle
                        logger.debug("Loaded lifecycle from memory", extra={"lifecycle": lifecycle})

                result.apply_system_memory(memories)
            except Exception as exc:
                logger.exception(
                    "Failed to load user memory",
                    extra={
                        "client_id": thread_snapshot.client_id,
                        "project_id": project_id,
                        "thread_id": thread_id,
                        "error": str(exc),
                        "error_type": type(exc).__name__,
                        "policy": "fallback_empty_memory",
                    },
                )
                result.user_memory = {}
        else:
            result.user_memory = {}

        logger.debug("State loaded", extra={"thread_id": thread_id, "message_count": len(recent_messages)})
        return result.to_state_patch()

    def _get_load_state_input_size(state: AgentState) -> int:
        return 0

    def _get_load_state_output_size(result: dict[str, Any]) -> int:
        return len(result.get("history", [])) + len(result.get("user_memory", {}))

    async def load_state_node(state: AgentState) -> dict[str, Any]:
        return await log_node_execution(
            "load_state",
            _load_state_node_impl,
            state,
            get_input_size=_get_load_state_input_size,
            get_output_size=_get_load_state_output_size,
        )

    return load_state_node
