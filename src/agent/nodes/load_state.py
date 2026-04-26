"""
Load-state node for the LangGraph pipeline.
"""

from collections.abc import Mapping
from typing import Any

from src.agent.state import AgentState
from src.infrastructure.db.repositories.memory_repository import MemoryRepository
from src.infrastructure.logging.logger import get_logger, log_node_execution

logger = get_logger(__name__)


def _read_value(view: Any, key: str, default: Any = None) -> Any:
    """
    Read from typed dataclass/view, mapping, or view exposing to_record().
    This is not a repository compatibility facade; it is read-model normalization
    at the node boundary.
    """
    if view is None:
        return default

    if isinstance(view, Mapping):
        return view.get(key, default)

    to_record = getattr(view, "to_record", None)
    if callable(to_record):
        record = to_record()
        if isinstance(record, Mapping):
            return record.get(key, default)

    return getattr(view, key, default)


def create_load_state_node(
    *,
    thread_read_repo,
    thread_message_repo,
    thread_runtime_state_repo,
    project_repo,
    memory_repo: MemoryRepository | None = None,
):
    """
    Create the load-state node with split thread repositories.
    """

    async def _load_state_node_impl(state: AgentState) -> dict[str, Any]:
        thread_id = state.get("thread_id")
        if not thread_id:
            logger.warning("load_state called without thread_id")
            return {}

        patch: dict[str, Any] = {
            "history": [],
            "user_memory": {},
        }

        thread_view = await thread_read_repo.get_thread_with_project_view(thread_id)
        if thread_view:
            patch["project_id"] = _read_value(thread_view, "project_id")
            patch["client_id"] = _read_value(thread_view, "client_id")
            patch["thread_status"] = _read_value(thread_view, "status")
            patch["conversation_summary"] = _read_value(thread_view, "context_summary")

        analytics_view = await thread_runtime_state_repo.get_analytics_view(thread_id)
        if analytics_view:
            patch["intent"] = _read_value(analytics_view, "intent")
            patch["lifecycle"] = _read_value(analytics_view, "lifecycle")
            patch["cta"] = _read_value(analytics_view, "cta")
            patch["decision"] = _read_value(analytics_view, "decision")

        recent_messages = await thread_message_repo.get_messages_for_langgraph(thread_id)
        patch["history"] = recent_messages

        persisted_state = await thread_runtime_state_repo.get_state_json(thread_id)
        if isinstance(persisted_state, dict):
            patch.update(persisted_state)

        project_id = patch.get("project_id") or state.get("project_id")
        client_id = patch.get("client_id") or state.get("client_id")

        if memory_repo and project_id and client_id:
            try:
                if hasattr(memory_repo, "get_for_user_view"):
                    patch["user_memory"] = await memory_repo.get_for_user_view(project_id, client_id)
                elif hasattr(memory_repo, "get_for_client"):
                    patch["user_memory"] = await memory_repo.get_for_client(project_id, client_id, limit=20)
                elif hasattr(memory_repo, "list_for_client"):
                    patch["user_memory"] = await memory_repo.list_for_client(project_id, client_id, limit=20)
            except Exception as exc:
                logger.exception(
                    "Failed to load client memory",
                    extra={
                        "thread_id": thread_id,
                        "project_id": project_id,
                        "client_id": client_id,
                        "error": str(exc),
                        "policy": "fallback_empty_memory",
                    },
                )
                patch["user_memory"] = {}

        return patch

    async def load_state_node(state: AgentState) -> dict[str, Any]:
        return await log_node_execution("load_state", _load_state_node_impl, state)

    return load_state_node
