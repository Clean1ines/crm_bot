"""
Graph creation and execution helpers.

This module owns the application-side runtime contract:
- concrete graph implementation is injected through AgentFactoryPort
- graph input is GraphExecutionRequestDto
- graph output is MessageProcessingOutcomeDto
- missing graph response has deterministic fallback behavior
"""

import json
from typing import Any, Union

from src.application.dto.runtime_dto import (
    GraphExecutionRequestDto,
    GraphExecutionResultDto,
    MessageProcessingOutcomeDto,
)
from src.application.ports.agent_runtime_port import AgentFactoryPort, AgentGraphRuntimePort


GRAPH_EMPTY_RESPONSE_FALLBACK_TEXT = "Sorry, I couldn't generate a response."


class GraphFactory:
    def __init__(
        self,
        *,
        agent_factory: AgentFactoryPort,
        tool_registry=None,
        thread_repo=None,
        queue_repo=None,
        event_repo=None,
        project_repo=None,
        memory_repo=None,
        logger,
    ) -> None:
        self.logger = logger
        self.agent = agent_factory(
            tool_registry=tool_registry,
            thread_repo=thread_repo,
            queue_repo=queue_repo,
            event_repo=event_repo,
            project_repo=project_repo,
            memory_repo=memory_repo,
        )

    def build_graph_from_json(self, graph_json: Union[str, dict[str, Any]]) -> AgentGraphRuntimePort:
        """
        Return the project graph.

        Dynamic graph JSON is intentionally not trusted yet. Invalid, empty, or
        unsupported definitions fall back to the compiled default agent.
        """
        if isinstance(graph_json, str):
            try:
                graph_dict = json.loads(graph_json)
            except json.JSONDecodeError as exc:
                self.logger.error("Invalid JSON in graph definition", extra={"error": str(exc)})
                return self.agent
        else:
            graph_dict = graph_json

        if not graph_dict or "nodes" not in graph_dict:
            self.logger.warning("Invalid or empty graph_json, using default agent")
            return self.agent

        self.logger.debug(
            "Building graph from JSON",
            extra={"node_count": len(graph_dict.get("nodes", []))},
        )
        return self.agent

    async def get_graph_for_project(self, project_id: str) -> AgentGraphRuntimePort:
        self.logger.debug("Loading graph for project", extra={"project_id": project_id})
        self.logger.debug("Using default agent graph", extra={"project_id": project_id})
        return self.agent


class GraphExecutor:
    RECENT_MESSAGES_LIMIT = 10

    def __init__(self, logger) -> None:
        self.logger = logger

    @staticmethod
    def outcome(text: str, *, delivered: bool = False) -> MessageProcessingOutcomeDto:
        return MessageProcessingOutcomeDto.create(text=text, delivered=delivered)

    def trim_recent_history(self, recent_messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if len(recent_messages) <= self.RECENT_MESSAGES_LIMIT:
            return recent_messages
        return recent_messages[-self.RECENT_MESSAGES_LIMIT:]

    def create_graph_execution_request(
        self,
        *,
        project_id: str,
        thread_id: str,
        chat_id: int,
        question: str,
        recent_history: list[dict[str, Any]],
        runtime_context,
        trace_id: str,
    ) -> GraphExecutionRequestDto:
        return GraphExecutionRequestDto(
            project_id=project_id,
            thread_id=thread_id,
            chat_id=chat_id,
            question=question,
            recent_history=recent_history,
            runtime_context=runtime_context,
            trace_id=trace_id,
        )

    def build_agent_state(self, *, request: GraphExecutionRequestDto) -> dict[str, Any]:
        """
        Convert the typed application request into the graph state contract.
        """
        return {
            "messages": [],
            "project_id": request.project_id,
            "thread_id": request.thread_id,
            "escalation_requested": False,
            "tool_calls": None,
            "user_input": request.question,
            "client_profile": None,
            "conversation_summary": "",
            "history": request.recent_history,
            "knowledge_chunks": None,
            "decision": None,
            "tool_name": None,
            "tool_args": None,
            "tool_result": None,
            "user_memory": None,
            "response_text": None,
            "requires_human": False,
            "confidence": None,
            "chat_id": request.chat_id,
            "message_sent": False,
            "trace_id": request.trace_id,
            "client_id": None,
            "project_configuration": request.runtime_context.to_dict(),
            "close_ticket": False,
            "intent": None,
            "cta": None,
            "lifecycle": None,
            "features": None,
            "dialog_state": None,
            "topic": None,
            "lead_status": None,
            "repeat_count": None,
        }

    def extract_graph_result(
        self,
        result_state: dict[str, Any],
        *,
        question: str,
        thread_id: str,
    ) -> GraphExecutionResultDto:
        result = GraphExecutionResultDto.from_graph_state(result_state)
        if result.delivered:
            self.logger.debug(
                f"Message sent for question: {question[:30]}...",
                extra={"thread_id": thread_id},
            )
            return result

        if result.response_text:
            return result

        self.logger.warning(
            f"Graph did not produce response_text for question: {question[:30]}...",
            extra={"thread_id": thread_id},
        )
        return GraphExecutionResultDto(response_text=GRAPH_EMPTY_RESPONSE_FALLBACK_TEXT)

    async def invoke_graph(
        self,
        *,
        graph: AgentGraphRuntimePort,
        request: GraphExecutionRequestDto,
    ) -> MessageProcessingOutcomeDto:
        state = self.build_agent_state(request=request)
        result_state = await graph.ainvoke(state)
        graph_result = self.extract_graph_result(
            result_state,
            question=request.question,
            thread_id=request.thread_id,
        )
        return self.outcome(
            graph_result.response_text,
            delivered=graph_result.delivered,
        )
