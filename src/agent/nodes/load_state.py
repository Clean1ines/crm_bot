"""
Load state node for LangGraph pipeline.

Loads conversation history, summary, client profile, and long-term memory
from the database and populates the AgentState with this data.
"""

from typing import Dict, Any, Optional

from src.core.logging import get_logger, log_node_execution
from src.agent.state import AgentState
from src.database.repositories.memory_repository import MemoryRepository

logger = get_logger(__name__)


def create_load_state_node(thread_repo, project_repo, memory_repo: Optional[MemoryRepository] = None):
    """
    Factory function that creates a load_state node with injected repository dependencies.

    Args:
        thread_repo: ThreadRepository instance for accessing thread data.
        project_repo: ProjectRepository instance (may be used for project settings,
                      but not directly needed here).
        memory_repo: Optional MemoryRepository for loading long-term user memory.
                     If None, memory loading is skipped.

    Returns:
        An async function that takes an AgentState dict and returns a dict with
        loaded fields (client_profile, conversation_summary, history, user_memory).
    """
    async def _load_state_node_impl(state: AgentState) -> Dict[str, Any]:
        """
        Load conversation data from the database into the state.

        This node expects that `state` contains at least `thread_id` and `project_id`.
        It retrieves:
          - Recent messages (history)
          - Conversation summary
          - Client profile (if available in users table)
          - Previously saved state_json (if any)
          - Long-term user memory (if memory_repo provided)
          - Analytics fields from thread (intent, lifecycle, cta, decision)
          - Lifecycle from user memory (if not present in thread)
          - Dialog state fields (dialog_state, topic, lead_status, repeat_count) from memory

        Args:
            state: Current AgentState (may already contain some fields).

        Returns:
            A dictionary with the loaded fields that will be merged into the state.
            Returns an empty dict if thread_id or project_id is missing.
        """
        thread_id = state.get("thread_id")
        project_id = state.get("project_id")

        if not thread_id or not project_id:
            logger.error(
                "load_state_node called without thread_id or project_id",
                extra={"thread_id": thread_id, "project_id": project_id}
            )
            return {}

        logger.debug("Loading state", extra={"thread_id": thread_id, "project_id": project_id})

        # Load thread details including summary and client_id
        thread_data = await thread_repo.get_thread_with_project(thread_id)
        if not thread_data:
            logger.warning("Thread not found", extra={"thread_id": thread_id})
            return {}

        client_id = thread_data.get("client_id")
        if client_id and isinstance(client_id, str):
            client_id_str = str(client_id)
        else:
            client_id_str = None

        # Load analytics fields from thread
        analytics = await thread_repo.get_analytics(thread_id) if hasattr(thread_repo, "get_analytics") else None
        if analytics:
            logger.debug("Loaded analytics", extra={"thread_id": thread_id, "analytics": analytics})

        # Load recent messages (full history, but we'll keep a reasonable limit)
        recent_messages = await thread_repo.get_messages_for_langgraph(thread_id)
        if len(recent_messages) > 10:
            recent_messages = recent_messages[-10:]

        # Load saved state_json if any
        saved_state = await thread_repo.get_state_json(thread_id)

        # Prepare client profile (placeholder – will be filled from users table later)
        client_profile = None
        # TODO: load from users table using client_id from thread_data

        result = {
            "client_profile": client_profile,
            "conversation_summary": thread_data.get("context_summary"),
            "history": recent_messages,
            "knowledge_chunks": None,  # will be filled by kb_search node
            "client_id": client_id_str,
        }

        # Add analytics if present
        if analytics:
            if analytics.get("intent") is not None:
                result["intent"] = analytics["intent"]
            if analytics.get("lifecycle") is not None:
                result["lifecycle"] = analytics["lifecycle"]
            if analytics.get("cta") is not None:
                result["cta"] = analytics["cta"]
            if analytics.get("decision") is not None:
                result["decision"] = analytics["decision"]

        # Load long-term memory if available
        if memory_repo and client_id_str:
            try:
                # Fetch memory entries (e.g., preferences, facts)
                memories = await memory_repo.get_for_user(
                    project_id=project_id,
                    client_id=client_id_str,
                    limit=50
                )
                # Group by type for easier use in prompt
                memory_by_type: Dict[str, list] = {}
                for mem in memories:
                    t = mem["type"]
                    memory_by_type.setdefault(t, []).append({
                        "key": mem["key"],
                        "value": mem["value"]
                    })
                result["user_memory"] = memory_by_type
                logger.debug("Loaded user memory", extra={"client_id": client_id_str, "memory_count": len(memories)})

                # Also load lifecycle from memory if not already set from thread
                if "lifecycle" not in result:
                    lifecycle = await memory_repo.get_lifecycle(project_id, client_id_str)
                    if lifecycle:
                        result["lifecycle"] = lifecycle
                        logger.debug("Loaded lifecycle from memory", extra={"lifecycle": lifecycle})

                # Extract dialog state fields (type='system')
                for mem in memories:
                    if mem["type"] == "system":
                        key = mem["key"]
                        value = mem["value"]
                        if key == "dialog_state":
                            result["dialog_state"] = value
                        elif key == "topic":
                            result["topic"] = value
                        elif key == "lead_status":
                            result["lead_status"] = value
                        elif key == "repeat_count":
                            # Ensure it's an integer
                            try:
                                result["repeat_count"] = int(value) if value is not None else 0
                            except (TypeError, ValueError):
                                result["repeat_count"] = 0
                        # Add other system keys as needed

            except Exception as e:
                logger.exception("Failed to load user memory", extra={"client_id": client_id_str})
                result["user_memory"] = {}
        else:
            result["user_memory"] = {}

        # If saved_state exists and is a dict, we could merge it, but for now we ignore
        # because the new graph doesn't rely on saved_state yet.

        logger.debug("State loaded", extra={"thread_id": thread_id, "message_count": len(recent_messages)})
        return result

    def _get_load_state_input_size(state: AgentState) -> int:
        return 0  # no meaningful input size

    def _get_load_state_output_size(result: Dict[str, Any]) -> int:
        return len(result.get("history", [])) + len(result.get("user_memory", {}))

    async def load_state_node(state: AgentState) -> Dict[str, Any]:
        return await log_node_execution(
            "load_state",
            _load_state_node_impl,
            state,
            get_input_size=_get_load_state_input_size,
            get_output_size=_get_load_state_output_size
        )

    return load_state_node
