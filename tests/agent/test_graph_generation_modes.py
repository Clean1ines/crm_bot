from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agent import graph as graph_module
from src.agent.nodes.response_generator import create_response_generator_node
from src.domain.runtime.tool_execution import ToolExecutionOutcome, ToolExecutionStatus


class FakeToolRegistry:
    def __init__(self, *, tool_result=None, raise_tool=False):
        self.tool_result = tool_result or ToolExecutionOutcome.succeeded(
            payload={"ok": True, "text": "tool result"}
        )
        self.raise_tool = raise_tool
        self.calls = []
        self.ticket_tool = MagicMock()
        self.ticket_tool.run = AsyncMock(
            return_value=ToolExecutionOutcome.succeeded(
                payload={"ticket_id": "ticket-1"}
            )
        )

    def get_tool(self, name):
        if name == "ticket.create":
            return self.ticket_tool
        return None

    async def execute(self, name, args, context=None):
        self.calls.append((name, args, context))
        if name == "telegram.send_message":
            return ToolExecutionOutcome.succeeded(payload={"ok": True})
        if self.raise_tool:
            raise RuntimeError("tool down")
        return self.tool_result


class RuntimeStateRepo:
    def __init__(self):
        self.state = None
        self.save_state_json = AsyncMock(side_effect=self._save_state_json)
        self.update_analytics = AsyncMock()
        self.get_analytics_view = AsyncMock(return_value=None)

    async def _save_state_json(self, _thread_id, state):
        self.state = dict(state)

    async def get_state_json(self, _thread_id):
        return dict(self.state or {})


def _repo_bundle():
    thread_lifecycle_repo = MagicMock()
    thread_lifecycle_repo.update_status = AsyncMock()
    thread_message_repo = MagicMock()
    thread_message_repo.add_message = AsyncMock()
    thread_runtime_state_repo = MagicMock()
    thread_runtime_state_repo.save_state_json = AsyncMock()
    thread_runtime_state_repo.update_analytics = AsyncMock()
    thread_read_repo = MagicMock()
    thread_read_repo.get_thread_with_project_view = AsyncMock(return_value=None)
    queue_repo = MagicMock()
    queue_repo.enqueue = AsyncMock()
    return {
        "thread_lifecycle_repo": thread_lifecycle_repo,
        "thread_message_repo": thread_message_repo,
        "thread_runtime_state_repo": thread_runtime_state_repo,
        "thread_read_repo": thread_read_repo,
        "queue_repo": queue_repo,
    }


def _repo_bundle_with_runtime_state():
    repos = _repo_bundle()
    runtime_state_repo = RuntimeStateRepo()
    repos["thread_runtime_state_repo"] = runtime_state_repo
    repos["thread_read_repo"].get_thread_with_project_view = AsyncMock(
        return_value={
            "project_id": "project-1",
            "client_id": "client-1",
            "status": "active",
            "context_summary": None,
        }
    )
    repos["thread_message_repo"].get_messages_for_langgraph = AsyncMock(return_value=[])
    return repos, runtime_state_repo


def _patch_common_nodes(monkeypatch, *, policy_patch, response_seen, kb_called=None):
    def load_state_node_factory(**_kwargs):
        async def node(_state):
            return {}

        return node

    def intent_node_factory(*_args, **_kwargs):
        async def node(_state):
            return {}

        return node

    def policy_node_factory(*_args, **_kwargs):
        async def node(_state):
            return dict(policy_patch)

        return node

    def response_node_factory(*_args, **_kwargs):
        async def node(state):
            response_seen.append(dict(state))
            return {
                "response_text": "generated from " + str(state.get("generation_mode")),
                "requires_human": False,
            }

        return node

    def kb_node_factory(_registry):
        async def node(_state):
            if kb_called is not None:
                kb_called.append(True)
            return {"knowledge_chunks": [], "knowledge_retrieval_status": "empty"}

        return node

    monkeypatch.setattr(graph_module, "create_load_state_node", load_state_node_factory)
    monkeypatch.setattr(
        graph_module, "create_intent_extractor_node", intent_node_factory
    )
    monkeypatch.setattr(graph_module, "create_policy_engine_node", policy_node_factory)
    monkeypatch.setattr(
        graph_module, "create_response_generator_node", response_node_factory
    )
    monkeypatch.setattr(graph_module, "create_kb_search_node", kb_node_factory)


@pytest.mark.asyncio
async def test_compiled_graph_missing_tool_selection_fails_without_escalation(
    monkeypatch,
):
    response_seen = []
    _patch_common_nodes(
        monkeypatch,
        policy_patch={
            "decision": "CALL_TOOL",
            "tool_args": {"name": "Alice"},
            "requires_human": False,
        },
        response_seen=response_seen,
    )
    repos = _repo_bundle()
    registry = FakeToolRegistry()
    agent = graph_module.create_agent(tool_registry=registry, **repos)

    result = await agent.ainvoke(
        {
            "project_id": "project-1",
            "thread_id": "thread-1",
            "client_id": "client-1",
            "chat_id": 1,
            "user_input": "lookup",
            "requires_human": False,
        }
    )

    assert response_seen
    assert response_seen[-1]["tool_execution_status"] == "failed"
    assert (
        response_seen[-1]["tool_execution_safe_error_code"] == "missing_tool_selection"
    )
    assert response_seen[-1]["generation_mode"] == "TOOL_RESULT_RESPONSE"
    assert response_seen[-1]["requires_human"] is False
    assert result["requires_human"] is False
    repos["queue_repo"].enqueue.assert_not_awaited()


@pytest.mark.asyncio
async def test_compiled_graph_successful_call_tool_path_sets_tool_generation_mode(
    monkeypatch,
):
    response_seen = []
    _patch_common_nodes(
        monkeypatch,
        policy_patch={
            "decision": "CALL_TOOL",
            "tool_name": "crm.lookup",
            "tool_args": {"name": "Alice"},
            "requires_human": False,
        },
        response_seen=response_seen,
    )
    repos = _repo_bundle()
    registry = FakeToolRegistry(
        tool_result=ToolExecutionOutcome.succeeded(
            payload={"ok": True, "text": "found Alice"}
        )
    )
    agent = graph_module.create_agent(tool_registry=registry, **repos)

    result = await agent.ainvoke(
        {
            "project_id": "project-1",
            "thread_id": "thread-1",
            "client_id": "client-1",
            "chat_id": 1,
            "user_input": "lookup",
            "requires_human": False,
        }
    )

    assert response_seen
    assert response_seen[-1]["tool_result"] == {"ok": True, "text": "found Alice"}
    assert response_seen[-1]["tool_execution_status"] == "succeeded"
    assert response_seen[-1]["generation_mode"] == "TOOL_RESULT_RESPONSE"
    assert result["requires_human"] is False


@pytest.mark.asyncio
async def test_compiled_graph_tool_exception_policy_is_failed_not_handoff(monkeypatch):
    response_seen = []
    _patch_common_nodes(
        monkeypatch,
        policy_patch={
            "decision": "CALL_TOOL",
            "tool_name": "crm.lookup",
            "tool_args": {"name": "Alice"},
            "requires_human": False,
        },
        response_seen=response_seen,
    )
    repos = _repo_bundle()
    registry = FakeToolRegistry(raise_tool=True)
    agent = graph_module.create_agent(tool_registry=registry, **repos)

    result = await agent.ainvoke(
        {
            "project_id": "project-1",
            "thread_id": "thread-1",
            "client_id": "client-1",
            "chat_id": 1,
            "user_input": "lookup",
            "requires_human": False,
        }
    )

    assert response_seen
    assert response_seen[-1]["tool_execution_status"] == "failed"
    assert response_seen[-1]["generation_mode"] == "TOOL_RESULT_RESPONSE"
    assert response_seen[-1]["requires_human"] is False
    assert result["requires_human"] is False
    repos["queue_repo"].enqueue.assert_not_awaited()


@pytest.mark.asyncio
async def test_compiled_graph_requires_human_tool_outcome_routes_to_escalate_not_generator(
    monkeypatch,
):
    response_seen = []
    _patch_common_nodes(
        monkeypatch,
        policy_patch={
            "decision": "CALL_TOOL",
            "tool_name": "crm.lookup",
            "tool_args": {"name": "Alice"},
            "requires_human": False,
        },
        response_seen=response_seen,
    )
    repos = _repo_bundle()
    registry = FakeToolRegistry(
        tool_result=ToolExecutionOutcome(
            status=ToolExecutionStatus.REQUIRES_HUMAN,
            response_text="Manual help needed",
        )
    )
    agent = graph_module.create_agent(tool_registry=registry, **repos)

    result = await agent.ainvoke(
        {
            "project_id": "project-1",
            "thread_id": "thread-1",
            "client_id": "client-1",
            "chat_id": 1,
            "user_input": "lookup",
            "requires_human": False,
        }
    )

    assert response_seen == []
    assert result["requires_human"] is True
    repos["queue_repo"].enqueue.assert_awaited()


@pytest.mark.asyncio
async def test_compiled_graph_conversational_mode_bypasses_kb(monkeypatch):
    response_seen = []
    kb_called = []
    _patch_common_nodes(
        monkeypatch,
        policy_patch={
            "decision": "LLM_GENERATE",
            "generation_mode": "CONVERSATIONAL_RESPONSE",
            "knowledge_retrieval_status": "skipped",
            "requires_human": False,
        },
        response_seen=response_seen,
        kb_called=kb_called,
    )
    repos = _repo_bundle()
    registry = FakeToolRegistry()
    agent = graph_module.create_agent(tool_registry=registry, **repos)

    await agent.ainvoke(
        {
            "project_id": "project-1",
            "thread_id": "thread-1",
            "client_id": "client-1",
            "chat_id": 1,
            "user_input": "thanks",
            "requires_human": False,
        }
    )

    assert kb_called == []
    assert response_seen[-1]["generation_mode"] == "CONVERSATIONAL_RESPONSE"
    repos["thread_message_repo"].add_message.assert_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("generation_mode", [None, "garbage"])
async def test_compiled_graph_invalid_llm_generation_mode_bypasses_kb(
    monkeypatch, generation_mode
):
    response_seen = []
    kb_called = []
    _patch_common_nodes(
        monkeypatch,
        policy_patch={
            "decision": "LLM_GENERATE",
            "generation_mode": generation_mode,
            "requires_human": False,
        },
        response_seen=response_seen,
        kb_called=kb_called,
    )
    repos = _repo_bundle()
    registry = FakeToolRegistry()
    agent = graph_module.create_agent(tool_registry=registry, **repos)

    await agent.ainvoke(
        {
            "project_id": "project-1",
            "thread_id": "thread-1",
            "client_id": "client-1",
            "chat_id": 1,
            "user_input": "question",
            "requires_human": False,
        }
    )

    assert kb_called == []
    assert response_seen
    assert response_seen[-1].get("generation_mode") == generation_mode


@pytest.mark.asyncio
async def test_compiled_graph_valid_knowledge_mode_routes_to_kb(monkeypatch):
    response_seen = []
    kb_called = []
    _patch_common_nodes(
        monkeypatch,
        policy_patch={
            "decision": "LLM_GENERATE",
            "generation_mode": "KNOWLEDGE_ANSWER",
            "requires_human": False,
        },
        response_seen=response_seen,
        kb_called=kb_called,
    )
    repos = _repo_bundle()
    registry = FakeToolRegistry()
    agent = graph_module.create_agent(tool_registry=registry, **repos)

    await agent.ainvoke(
        {
            "project_id": "project-1",
            "thread_id": "thread-1",
            "client_id": "client-1",
            "chat_id": 1,
            "user_input": "question",
            "requires_human": False,
        }
    )

    assert kb_called == [True]
    assert response_seen[-1]["generation_mode"] == "KNOWLEDGE_ANSWER"


@pytest.mark.asyncio
async def test_compiled_graph_invalid_evidence_ref_repairs_to_valid_alias(monkeypatch):
    response_patches = []
    llm = MagicMock()
    llm.ainvoke = AsyncMock(
        side_effect=[
            MagicMock(
                content=(
                    '{"answerability":"supported","answer":"Непроверенный ответ.",'
                    '"supporting_evidence_refs":["E999"],"unsupported_aspects":[]}'
                )
            ),
            MagicMock(
                content=(
                    '{"answerability":"supported","answer":"Подтверждённый ответ.",'
                    '"supporting_evidence_refs":["E1"],"unsupported_aspects":[]}'
                )
            ),
        ]
    )

    def load_state_node_factory(**_kwargs):
        async def node(_state):
            return {}

        return node

    def intent_node_factory(*_args, **_kwargs):
        async def node(_state):
            return {}

        return node

    def policy_node_factory(*_args, **_kwargs):
        async def node(_state):
            return {
                "decision": "LLM_GENERATE",
                "generation_mode": "KNOWLEDGE_ANSWER",
                "requires_human": False,
            }

        return node

    def kb_node_factory(_registry):
        async def node(_state):
            return {
                "knowledge_chunks": [
                    {
                        "id": "draft-claim-curation-runtime-entry:entry-1",
                        "score": 0.9,
                        "content": "Подтверждённый ответ.",
                    }
                ],
                "knowledge_retrieval_status": "retrieved",
            }

        return node

    monkeypatch.setattr(graph_module, "create_load_state_node", load_state_node_factory)
    monkeypatch.setattr(
        graph_module, "create_intent_extractor_node", intent_node_factory
    )
    monkeypatch.setattr(graph_module, "create_policy_engine_node", policy_node_factory)
    monkeypatch.setattr(graph_module, "create_kb_search_node", kb_node_factory)
    monkeypatch.setattr(
        graph_module,
        "create_response_generator_node",
        lambda: _capturing_response_node(llm, response_patches),
    )

    repos = _repo_bundle()
    registry = FakeToolRegistry()
    agent = graph_module.create_agent(tool_registry=registry, **repos)

    await agent.ainvoke(
        {
            "project_id": "project-1",
            "thread_id": "thread-1",
            "client_id": "client-1",
            "chat_id": 1,
            "user_input": "Что известно?",
            "project_configuration": {"settings": {"target_language": "ru"}},
            "requires_human": False,
        }
    )

    sent_messages = [
        args["text"]
        for name, args, _context in registry.calls
        if name == "telegram.send_message"
    ]
    assert sent_messages == ["Подтверждённый ответ."]
    response_patch = response_patches[-1]
    assert response_patch["metadata"]["generation_attempt_count"] == 2
    assert response_patch["metadata"]["initial_validation_failure_reason"] == (
        "invalid_supporting_evidence_refs"
    )
    assert response_patch["metadata"]["repair_attempted"] is True
    assert response_patch["metadata"]["repair_succeeded"] is True
    assert response_patch["metadata"]["repair_validation_failure_reason"] is None
    assert response_patch["model_evidence_refs"] == ["E1"]
    assert response_patch["supporting_entry_ids"] == [
        "draft-claim-curation-runtime-entry:entry-1"
    ]
    assert llm.ainvoke.await_count == 2
    first_prompt = llm.ainvoke.await_args_list[0].args[0][0][1]
    repair_prompt = llm.ainvoke.await_args_list[1].args[0][0][1]
    assert "draft-claim-curation-runtime-entry:" not in first_prompt
    assert "Allowed evidence refs: E1" in repair_prompt
    repair_section = repair_prompt.split("The previous response did not satisfy", 1)[1]
    assert "draft-claim-curation-runtime-entry:" not in repair_section


def _capturing_response_node(llm, response_patches):
    real_node = create_response_generator_node(llm=llm, model_name="base-model")

    async def node(state):
        patch = await real_node(state)
        response_patches.append(dict(patch))
        return patch

    return node


@pytest.mark.asyncio
async def test_compiled_graph_second_turn_clears_stale_tool_state(monkeypatch):
    response_seen = []
    kb_called = []
    policy_patches = [
        {
            "decision": "CALL_TOOL",
            "tool_name": "crm.lookup",
            "tool_args": {"name": "Alice"},
            "requires_human": False,
        },
        {
            "decision": "LLM_GENERATE",
            "generation_mode": "KNOWLEDGE_ANSWER",
            "tool_result": None,
            "tool_execution_status": None,
            "tool_execution_safe_error_code": None,
            "knowledge_retrieval_status": "retrieved",
            "knowledge_chunks": [{"id": "entry-1", "score": 0.9, "content": "KB fact"}],
            "requires_human": False,
        },
    ]

    def load_state_node_factory(**_kwargs):
        async def node(_state):
            return {}

        return node

    def intent_node_factory(*_args, **_kwargs):
        async def node(_state):
            return {}

        return node

    def policy_node_factory(*_args, **_kwargs):
        async def node(_state):
            return dict(policy_patches.pop(0))

        return node

    def response_node_factory(*_args, **_kwargs):
        async def node(state):
            response_seen.append(dict(state))
            return {"response_text": "ok", "requires_human": False}

        return node

    def kb_node_factory(_registry):
        async def node(_state):
            kb_called.append(True)
            return {
                "knowledge_chunks": [
                    {"id": "entry-1", "score": 0.9, "content": "KB fact"}
                ],
                "knowledge_retrieval_status": "retrieved",
            }

        return node

    monkeypatch.setattr(graph_module, "create_load_state_node", load_state_node_factory)
    monkeypatch.setattr(
        graph_module, "create_intent_extractor_node", intent_node_factory
    )
    monkeypatch.setattr(graph_module, "create_policy_engine_node", policy_node_factory)
    monkeypatch.setattr(
        graph_module, "create_response_generator_node", response_node_factory
    )
    monkeypatch.setattr(graph_module, "create_kb_search_node", kb_node_factory)

    repos = _repo_bundle()
    registry = FakeToolRegistry(
        tool_result=ToolExecutionOutcome.succeeded(
            payload={"ok": True, "text": "found Alice"}
        )
    )
    agent = graph_module.create_agent(tool_registry=registry, **repos)

    first = await agent.ainvoke(
        {
            "project_id": "project-",
            "thread_id": "thread-",
            "client_id": "client-",
            "chat_id": 1,
            "user_input": "lookup",
            "requires_human": False,
        }
    )
    second = await agent.ainvoke(
        {
            "project_id": "project-",
            "thread_id": "thread-",
            "client_id": "client-",
            "chat_id": 1,
            "user_input": "factual question",
            "requires_human": False,
            "generation_mode": first.get("generation_mode"),
            "tool_result": first.get("tool_result"),
            "tool_execution_status": first.get("tool_execution_status"),
        }
    )

    assert response_seen[0]["generation_mode"] == "TOOL_RESULT_RESPONSE"
    assert response_seen[0]["tool_result"] == {"ok": True, "text": "found Alice"}
    assert response_seen[1]["generation_mode"] == "KNOWLEDGE_ANSWER"
    assert response_seen[1].get("tool_result") is None
    assert response_seen[1].get("tool_execution_status") is None
    assert second["generation_mode"] == "KNOWLEDGE_ANSWER"
    assert kb_called == [True]


@pytest.mark.asyncio
async def test_compiled_graph_status_failure_persists_partial_state_and_next_turn_recovers(
    monkeypatch,
):
    def intent_node_factory(*_args, **_kwargs):
        async def node(state):
            if state.get("user_input") == "Что умеет Axole?":
                return {
                    "domain": "business",
                    "intent": "other",
                    "topic": "product",
                    "cta": "none",
                    "turn_relation": "new_topic",
                    "is_repeat_like": False,
                    "should_search_kb": True,
                    "should_generate_answer": True,
                    "should_offer_manager": False,
                }
            return {}

        return node

    monkeypatch.setattr(
        graph_module, "create_intent_extractor_node", intent_node_factory
    )
    repos, runtime_state_repo = _repo_bundle_with_runtime_state()
    repos["thread_lifecycle_repo"].update_status = AsyncMock(
        side_effect=RuntimeError("status write failed")
    )
    registry = FakeToolRegistry()
    registry.ticket_tool.run = AsyncMock(
        return_value=ToolExecutionOutcome.succeeded(payload={"ticket_id": "ticket-123"})
    )
    registry.tool_result = ToolExecutionOutcome.succeeded(payload={"results": []})
    agent = graph_module.create_agent(tool_registry=registry, **repos)

    first = await agent.ainvoke(
        {
            "project_id": "project-1",
            "thread_id": "thread-1",
            "client_id": "client-1",
            "chat_id": 1,
            "user_input": "Да",
            "lifecycle": "active_client",
            "resolved_cta": "call_manager",
            "resolved_cta_reply": "affirmative",
            "turn_relation": "continuation",
            "dialog_state": {
                "last_intent": "product",
                "last_topic": "product",
                "last_cta": "call_manager",
                "repeat_count": 0,
                "lead_status": "active_client",
                "lifecycle": "active_client",
                "handoff_confirmation_pending": False,
            },
            "requires_human": False,
        }
    )

    assert first["requires_human"] is False
    assert first["escalation_failed"] is True
    assert first["ticket_created"] is True
    assert first["handoff_ticket_id"] == "ticket-123"
    assert first.get("technical_ticket_id") is None
    assert first["handoff_completed"] is False
    assert first["thread_waiting_manager"] is False
    assert first["notification_degraded"] is False
    repos["thread_lifecycle_repo"].update_status.assert_awaited_once()
    repos["queue_repo"].enqueue.assert_not_awaited()

    persisted = runtime_state_repo.state
    assert persisted is not None
    assert persisted["handoff_ticket_id"] == "ticket-123"
    assert persisted["ticket_created"] is True
    assert persisted["escalation_failed"] is True
    assert persisted["handoff_completed"] is False
    assert persisted["thread_waiting_manager"] is False
    assert persisted["notification_degraded"] is False
    assert persisted["requires_human"] is False
    assert "response_text" not in persisted
    assert "tool_result" not in persisted
    assert "tool_name" not in persisted
    assert "tool_args" not in persisted
    assert "generation_mode" not in persisted
    assert "tool_execution_status" not in persisted
    assert "tool_execution_safe_error_code" not in persisted

    repos["thread_lifecycle_repo"].update_status.reset_mock()
    second = await agent.ainvoke(
        {
            "thread_id": "thread-1",
            "chat_id": 1,
            "user_input": "Что умеет Axole?",
        }
    )

    assert second["decision"] == "LLM_GENERATE"
    assert second["generation_mode"] == "KNOWLEDGE_ANSWER"
    assert second["requires_human"] is False
    assert second["handoff_ticket_id"] == "ticket-123"
    assert second["ticket_created"] is True
    assert second["escalation_failed"] is True
    assert second["handoff_completed"] is False
    assert second["thread_waiting_manager"] is False
    assert second["notification_degraded"] is False
    assert second.get("tool_result") is None
    repos["thread_lifecycle_repo"].update_status.assert_not_awaited()


@pytest.mark.asyncio
async def test_compiled_graph_preserves_kb_retrieval_status_for_generator(
    monkeypatch,
):
    response_seen = []

    def load_state_node_factory(**_kwargs):
        async def node(_state):
            return {}

        return node

    def intent_node_factory(*_args, **_kwargs):
        async def node(_state):
            return {}

        return node

    def policy_node_factory(*_args, **_kwargs):
        async def node(_state):
            return {
                "decision": "LLM_GENERATE",
                "generation_mode": "KNOWLEDGE_ANSWER",
                "should_search_kb": True,
                "should_generate_answer": True,
                "requires_human": False,
            }

        return node

    def kb_node_factory(_registry):
        async def node(_state):
            return {
                "knowledge_chunks": [
                    {
                        "id": "entry-1",
                        "score": 0.9,
                        "content": "Axole is a business knowledge and support platform.",
                    }
                ],
                "knowledge_retrieval_status": "retrieved",
                "knowledge_retrieval_error_type": None,
            }

        return node

    def response_node_factory(*_args, **_kwargs):
        async def node(state):
            response_seen.append(dict(state))
            return {
                "response_text": "ok",
                "requires_human": False,
            }

        return node

    monkeypatch.setattr(
        graph_module,
        "create_load_state_node",
        load_state_node_factory,
    )
    monkeypatch.setattr(
        graph_module,
        "create_intent_extractor_node",
        intent_node_factory,
    )
    monkeypatch.setattr(
        graph_module,
        "create_policy_engine_node",
        policy_node_factory,
    )
    monkeypatch.setattr(
        graph_module,
        "create_kb_search_node",
        kb_node_factory,
    )
    monkeypatch.setattr(
        graph_module,
        "create_response_generator_node",
        response_node_factory,
    )

    repos = _repo_bundle()
    agent = graph_module.create_agent(
        tool_registry=FakeToolRegistry(),
        **repos,
    )

    await agent.ainvoke(
        {
            "project_id": "project-1",
            "thread_id": "thread-1",
            "client_id": "client-1",
            "chat_id": 1,
            "user_input": "Что такое Axole?",
            "requires_human": False,
        }
    )

    assert response_seen
    assert response_seen[-1]["generation_mode"] == "KNOWLEDGE_ANSWER"
    assert response_seen[-1]["knowledge_retrieval_status"] == "retrieved"
    assert response_seen[-1]["knowledge_retrieval_error_type"] is None
    assert response_seen[-1]["knowledge_chunks"] == [
        {
            "id": "entry-1",
            "score": 0.9,
            "content": "Axole is a business knowledge and support platform.",
        }
    ]
