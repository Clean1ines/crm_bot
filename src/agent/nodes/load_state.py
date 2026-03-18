"""
Load state node for LangGraph pipeline.

Loads conversation history, summary, and client profile from the database
and populates the AgentState with this data.
"""

from typing import Dict, Any, Optional

from src.core.logging import get_logger
from src.agent.state import AgentState

logger = get_logger(__name__)


def create_load_state_node(thread_repo, project_repo):
    """
    Factory function that creates a load_state node with injected repository dependencies.

    Args:
        thread_repo: ThreadRepository instance for accessing thread data.
        project_repo: ProjectRepository instance (may be used for project settings,
                      but not directly needed here).

    Returns:
        An async function that takes an AgentState dict and returns a dict with
        loaded fields (client_profile, conversation_summary, history).
    """

    async def load_state_node(state: AgentState) -> Dict[str, Any]:
        """
        Load conversation data from the database into the state.

        This node expects that `state` contains at least `thread_id` and `project_id`.
        It retrieves:
          - Recent messages (history)
          - Conversation summary
          - Client profile (if available in users table)
          - Previously saved state_json (if any)

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

        # Load thread details including summary
        thread_data = await thread_repo.get_thread_with_project(thread_id)
        if not thread_data:
            logger.warning("Thread not found", extra={"thread_id": thread_id})
            return {}

        # Load recent messages (full history, but we'll keep a reasonable limit)
        # We'll use the same limit as orchestrator (e.g., 10)
        recent_messages = await thread_repo.get_messages_for_langgraph(thread_id)
        # Limit to last 10 messages
        if len(recent_messages) > 10:
            recent_messages = recent_messages[-10:]

        # Load saved state_json if any
        saved_state = await thread_repo.get_state_json(thread_id)

        # Prepare client profile (placeholder – will be filled from users table later)
        client_profile = None
        # TODO: load from users table using client_id from thread_data

        # Prepare return dict with loaded fields
        result = {
            "client_profile": client_profile,
            "conversation_summary": thread_data.get("context_summary"),
            "history": recent_messages,
            "knowledge_chunks": None,  # will be filled by kb_search node
        }

        # If saved_state exists and is a dict, we could merge it, but for now we ignore
        # because the new graph doesn't rely on saved_state yet.

        logger.debug("State loaded", extra={"thread_id": thread_id, "message_count": len(recent_messages)})
        return result

    return load_state_node
