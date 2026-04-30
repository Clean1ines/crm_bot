"""
Runtime graph contract for the agent pipeline.

This module is pure domain/runtime contract:
- no LangGraph imports
- no infrastructure imports
- no application imports

It describes the allowed graph states, transitions, side effects, dependency
roles, and fallback policies that concrete graph adapters must implement.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping


class AgentGraphNode(StrEnum):
    LOAD_STATE = "load_state"
    RULES_CHECK = "rules_check"
    INTENT_EXTRACTOR = "intent_extractor"
    POLICY_ENGINE = "policy_engine"
    KB_SEARCH = "kb_search"
    TOOL_EXECUTOR = "tool_executor"
    ESCALATE = "escalate"
    RESPONSE_GENERATOR = "response_generator"
    RESPONDER = "responder"
    PERSIST = "persist"


class AgentGraphDecision(StrEnum):
    RESPOND = "RESPOND"
    ESCALATE = "ESCALATE"
    PROCEED_TO_LLM = "PROCEED_TO_LLM"
    LLM_GENERATE = "LLM_GENERATE"
    RESPOND_KB = "RESPOND_KB"
    RESPOND_TEMPLATE = "RESPOND_TEMPLATE"
    CALL_TOOL = "CALL_TOOL"
    ESCALATE_TO_HUMAN = "ESCALATE_TO_HUMAN"


class AgentGraphSideEffect(StrEnum):
    LOAD_THREAD_STATE = "load_thread_state"
    LOAD_USER_MEMORY = "load_user_memory"
    CALL_INTENT_LLM = "call_intent_llm"
    SEARCH_KNOWLEDGE = "search_knowledge"
    CALL_RESPONSE_LLM = "call_response_llm"
    EXECUTE_TOOL = "execute_tool"
    CREATE_ESCALATION_TICKET = "create_escalation_ticket"
    ENQUEUE_MANAGER_NOTIFICATION = "enqueue_manager_notification"
    ENQUEUE_METRICS_UPDATE = "enqueue_metrics_update"
    SEND_TELEGRAM_MESSAGE = "send_telegram_message"
    SAVE_ASSISTANT_MESSAGE = "save_assistant_message"
    SAVE_GRAPH_STATE = "save_graph_state"
    APPEND_EVENTS = "append_events"
    STORE_USER_MEMORY = "store_user_memory"
    UPDATE_ANALYTICS = "update_analytics"


class AgentGraphFallback(StrEnum):
    EMPTY_PATCH = "empty_patch"
    EMPTY_KNOWLEDGE = "empty_knowledge"
    EMPTY_USER_MEMORY = "empty_user_memory"
    HUMAN_HANDOFF = "human_handoff"
    USER_VISIBLE_ERROR = "user_visible_error"
    DELIVERED_WITH_PERSISTENCE_DEGRADED = "delivered_with_persistence_degraded"
    GENERATED_RESPONSE_MISSING = "generated_response_missing"


class AgentGraphDependency(StrEnum):
    TOOL_REGISTRY = "tool_registry"
    THREAD_REPOSITORY = "thread_repository"
    QUEUE_REPOSITORY = "queue_repository"
    EVENT_REPOSITORY = "event_repository"
    PROJECT_REPOSITORY = "project_repository"
    MEMORY_REPOSITORY = "memory_repository"
    INTENT_LLM = "intent_llm"
    RESPONSE_LLM = "response_llm"
    LOGGER = "logger"


@dataclass(frozen=True, slots=True)
class AgentGraphTransition:
    source: AgentGraphNode
    target: AgentGraphNode | None
    decision: AgentGraphDecision | None = None
    terminal: bool = False


@dataclass(frozen=True, slots=True)
class AgentGraphNodeContract:
    node: AgentGraphNode
    required_dependencies: tuple[AgentGraphDependency, ...] = ()
    optional_dependencies: tuple[AgentGraphDependency, ...] = ()
    side_effects: tuple[AgentGraphSideEffect, ...] = ()
    fallbacks: tuple[AgentGraphFallback, ...] = ()


@dataclass(frozen=True, slots=True)
class AgentGraphRuntimeContract:
    entrypoint: AgentGraphNode
    terminal_node: AgentGraphNode
    nodes: tuple[AgentGraphNode, ...]
    transitions: tuple[AgentGraphTransition, ...]
    node_contracts: Mapping[AgentGraphNode, AgentGraphNodeContract]

    def transition_map(self) -> dict[AgentGraphNode, tuple[AgentGraphTransition, ...]]:
        result: dict[AgentGraphNode, list[AgentGraphTransition]] = {}
        for transition in self.transitions:
            result.setdefault(transition.source, []).append(transition)
        return {node: tuple(items) for node, items in result.items()}

    def validate(self) -> None:
        declared_nodes = set(self.nodes)

        if self.entrypoint not in declared_nodes:
            raise ValueError(f"Graph entrypoint is not declared: {self.entrypoint}")

        if self.terminal_node not in declared_nodes:
            raise ValueError(
                f"Graph terminal node is not declared: {self.terminal_node}"
            )

        missing_contracts = declared_nodes - set(self.node_contracts)
        if missing_contracts:
            raise ValueError(f"Missing node contracts: {sorted(missing_contracts)}")

        for transition in self.transitions:
            if transition.source not in declared_nodes:
                raise ValueError(
                    f"Transition source is not declared: {transition.source}"
                )

            if (
                transition.target is not None
                and transition.target not in declared_nodes
            ):
                raise ValueError(
                    f"Transition target is not declared: {transition.target}"
                )

            if transition.terminal and transition.target is not None:
                raise ValueError("Terminal transitions must not have a target node")


AGENT_GRAPH_NODES: tuple[AgentGraphNode, ...] = (
    AgentGraphNode.LOAD_STATE,
    AgentGraphNode.RULES_CHECK,
    AgentGraphNode.INTENT_EXTRACTOR,
    AgentGraphNode.POLICY_ENGINE,
    AgentGraphNode.KB_SEARCH,
    AgentGraphNode.TOOL_EXECUTOR,
    AgentGraphNode.ESCALATE,
    AgentGraphNode.RESPONSE_GENERATOR,
    AgentGraphNode.RESPONDER,
    AgentGraphNode.PERSIST,
)


AGENT_GRAPH_TRANSITIONS: tuple[AgentGraphTransition, ...] = (
    AgentGraphTransition(AgentGraphNode.LOAD_STATE, AgentGraphNode.RULES_CHECK),
    AgentGraphTransition(
        AgentGraphNode.RULES_CHECK,
        AgentGraphNode.RESPONDER,
        AgentGraphDecision.RESPOND,
    ),
    AgentGraphTransition(
        AgentGraphNode.RULES_CHECK,
        AgentGraphNode.ESCALATE,
        AgentGraphDecision.ESCALATE,
    ),
    AgentGraphTransition(
        AgentGraphNode.RULES_CHECK,
        AgentGraphNode.INTENT_EXTRACTOR,
        AgentGraphDecision.PROCEED_TO_LLM,
    ),
    AgentGraphTransition(AgentGraphNode.INTENT_EXTRACTOR, AgentGraphNode.POLICY_ENGINE),
    AgentGraphTransition(
        AgentGraphNode.POLICY_ENGINE,
        AgentGraphNode.KB_SEARCH,
        AgentGraphDecision.LLM_GENERATE,
    ),
    AgentGraphTransition(
        AgentGraphNode.POLICY_ENGINE,
        AgentGraphNode.RESPONDER,
        AgentGraphDecision.RESPOND,
    ),
    AgentGraphTransition(
        AgentGraphNode.POLICY_ENGINE,
        AgentGraphNode.ESCALATE,
        AgentGraphDecision.ESCALATE_TO_HUMAN,
    ),
    AgentGraphTransition(
        AgentGraphNode.POLICY_ENGINE,
        AgentGraphNode.TOOL_EXECUTOR,
        AgentGraphDecision.CALL_TOOL,
    ),
    AgentGraphTransition(
        AgentGraphNode.POLICY_ENGINE,
        AgentGraphNode.ESCALATE,
        AgentGraphDecision.ESCALATE,
    ),
    AgentGraphTransition(AgentGraphNode.KB_SEARCH, AgentGraphNode.RESPONSE_GENERATOR),
    AgentGraphTransition(
        AgentGraphNode.TOOL_EXECUTOR, AgentGraphNode.RESPONSE_GENERATOR
    ),
    AgentGraphTransition(AgentGraphNode.TOOL_EXECUTOR, AgentGraphNode.ESCALATE),
    AgentGraphTransition(AgentGraphNode.ESCALATE, AgentGraphNode.RESPONDER),
    AgentGraphTransition(AgentGraphNode.RESPONSE_GENERATOR, AgentGraphNode.RESPONDER),
    AgentGraphTransition(AgentGraphNode.RESPONDER, AgentGraphNode.PERSIST),
    AgentGraphTransition(AgentGraphNode.PERSIST, None, terminal=True),
)


AGENT_GRAPH_NODE_CONTRACTS: Mapping[AgentGraphNode, AgentGraphNodeContract] = {
    AgentGraphNode.LOAD_STATE: AgentGraphNodeContract(
        node=AgentGraphNode.LOAD_STATE,
        required_dependencies=(AgentGraphDependency.THREAD_REPOSITORY,),
        optional_dependencies=(AgentGraphDependency.MEMORY_REPOSITORY,),
        side_effects=(
            AgentGraphSideEffect.LOAD_THREAD_STATE,
            AgentGraphSideEffect.LOAD_USER_MEMORY,
        ),
        fallbacks=(
            AgentGraphFallback.EMPTY_PATCH,
            AgentGraphFallback.EMPTY_USER_MEMORY,
        ),
    ),
    AgentGraphNode.RULES_CHECK: AgentGraphNodeContract(
        node=AgentGraphNode.RULES_CHECK,
        fallbacks=(AgentGraphFallback.EMPTY_PATCH,),
    ),
    AgentGraphNode.INTENT_EXTRACTOR: AgentGraphNodeContract(
        node=AgentGraphNode.INTENT_EXTRACTOR,
        optional_dependencies=(AgentGraphDependency.INTENT_LLM,),
        side_effects=(AgentGraphSideEffect.CALL_INTENT_LLM,),
        fallbacks=(AgentGraphFallback.EMPTY_PATCH,),
    ),
    AgentGraphNode.POLICY_ENGINE: AgentGraphNodeContract(
        node=AgentGraphNode.POLICY_ENGINE,
        optional_dependencies=(AgentGraphDependency.EVENT_REPOSITORY,),
        side_effects=(AgentGraphSideEffect.APPEND_EVENTS,),
        fallbacks=(AgentGraphFallback.EMPTY_PATCH,),
    ),
    AgentGraphNode.KB_SEARCH: AgentGraphNodeContract(
        node=AgentGraphNode.KB_SEARCH,
        required_dependencies=(AgentGraphDependency.TOOL_REGISTRY,),
        side_effects=(AgentGraphSideEffect.SEARCH_KNOWLEDGE,),
        fallbacks=(AgentGraphFallback.EMPTY_KNOWLEDGE,),
    ),
    AgentGraphNode.TOOL_EXECUTOR: AgentGraphNodeContract(
        node=AgentGraphNode.TOOL_EXECUTOR,
        required_dependencies=(AgentGraphDependency.TOOL_REGISTRY,),
        side_effects=(AgentGraphSideEffect.EXECUTE_TOOL,),
        fallbacks=(AgentGraphFallback.HUMAN_HANDOFF,),
    ),
    AgentGraphNode.ESCALATE: AgentGraphNodeContract(
        node=AgentGraphNode.ESCALATE,
        required_dependencies=(
            AgentGraphDependency.THREAD_REPOSITORY,
            AgentGraphDependency.QUEUE_REPOSITORY,
            AgentGraphDependency.TOOL_REGISTRY,
        ),
        side_effects=(
            AgentGraphSideEffect.CREATE_ESCALATION_TICKET,
            AgentGraphSideEffect.ENQUEUE_MANAGER_NOTIFICATION,
            AgentGraphSideEffect.ENQUEUE_METRICS_UPDATE,
        ),
        fallbacks=(AgentGraphFallback.HUMAN_HANDOFF,),
    ),
    AgentGraphNode.RESPONSE_GENERATOR: AgentGraphNodeContract(
        node=AgentGraphNode.RESPONSE_GENERATOR,
        optional_dependencies=(AgentGraphDependency.RESPONSE_LLM,),
        side_effects=(AgentGraphSideEffect.CALL_RESPONSE_LLM,),
        fallbacks=(AgentGraphFallback.USER_VISIBLE_ERROR,),
    ),
    AgentGraphNode.RESPONDER: AgentGraphNodeContract(
        node=AgentGraphNode.RESPONDER,
        required_dependencies=(AgentGraphDependency.TOOL_REGISTRY,),
        optional_dependencies=(AgentGraphDependency.THREAD_REPOSITORY,),
        side_effects=(
            AgentGraphSideEffect.SEND_TELEGRAM_MESSAGE,
            AgentGraphSideEffect.SAVE_ASSISTANT_MESSAGE,
        ),
        fallbacks=(
            AgentGraphFallback.HUMAN_HANDOFF,
            AgentGraphFallback.DELIVERED_WITH_PERSISTENCE_DEGRADED,
        ),
    ),
    AgentGraphNode.PERSIST: AgentGraphNodeContract(
        node=AgentGraphNode.PERSIST,
        required_dependencies=(AgentGraphDependency.THREAD_REPOSITORY,),
        optional_dependencies=(
            AgentGraphDependency.EVENT_REPOSITORY,
            AgentGraphDependency.MEMORY_REPOSITORY,
            AgentGraphDependency.QUEUE_REPOSITORY,
        ),
        side_effects=(
            AgentGraphSideEffect.SAVE_ASSISTANT_MESSAGE,
            AgentGraphSideEffect.SAVE_GRAPH_STATE,
            AgentGraphSideEffect.APPEND_EVENTS,
            AgentGraphSideEffect.STORE_USER_MEMORY,
            AgentGraphSideEffect.UPDATE_ANALYTICS,
            AgentGraphSideEffect.ENQUEUE_METRICS_UPDATE,
        ),
        fallbacks=(AgentGraphFallback.EMPTY_PATCH,),
    ),
}


AGENT_GRAPH_CONTRACT = AgentGraphRuntimeContract(
    entrypoint=AgentGraphNode.LOAD_STATE,
    terminal_node=AgentGraphNode.PERSIST,
    nodes=AGENT_GRAPH_NODES,
    transitions=AGENT_GRAPH_TRANSITIONS,
    node_contracts=AGENT_GRAPH_NODE_CONTRACTS,
)

AGENT_GRAPH_CONTRACT.validate()
