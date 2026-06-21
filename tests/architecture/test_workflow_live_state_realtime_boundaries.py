from __future__ import annotations

import ast
from pathlib import Path


KNOWLEDGE_HTTP_PATH = Path("src/interfaces/http/knowledge.py")


def _function_source(function_name: str) -> str:
    source = KNOWLEDGE_HTTP_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == function_name:
            segment = ast.get_source_segment(source, node)
            if segment is None:
                raise AssertionError(f"Could not extract source for {function_name}")
            return segment
    raise AssertionError(f"Function not found: {function_name}")


def test_live_state_read_endpoint_is_read_only_bootstrap_snapshot() -> None:
    source = _function_source("knowledge_workflow_live_state")

    assert "fetch_workbench_workflow_live_state" in source
    for forbidden_marker in (
        "BackgroundTasks",
        ".add_task",
        "_drain_workflow_from_live_state_poll",
        "make_knowledge_extraction_workflow_resume",
        "RunKnowledgeExtractionWorkflowResumeCommand",
        "llm_executor",
    ):
        assert forbidden_marker not in source


def test_snapshot_sse_is_compatibility_only_not_realtime_transport() -> None:
    source = _function_source("stream_knowledge_workflow_live_state_events")

    assert "workflow_live_state_deprecated" in source
    assert "frontend-events/stream" in source
    for forbidden_marker in (
        "fetch_workbench_workflow_live_state",
        "workflow_live_state_changed",
        "add_listener",
        "remove_listener",
        "_drain_workflow_from_live_state_poll",
        "make_knowledge_extraction_workflow_resume",
        "RunKnowledgeExtractionWorkflowResumeCommand",
    ):
        assert forbidden_marker not in source


def test_projection_frontend_events_read_endpoint_is_projection_only() -> None:
    source = _function_source("list_knowledge_frontend_workflow_events")

    assert "PostgresFrontendWorkflowEventRepository" in source
    for forbidden_marker in (
        "fetch_workbench_workflow_live_state",
        "workflow_live_state_changed",
        "_drain_workflow_from_live_state_poll",
        "make_knowledge_extraction_workflow_resume",
        "RunKnowledgeExtractionWorkflowResumeCommand",
        "BackgroundTasks",
        ".add_task",
    ):
        assert forbidden_marker not in source


def test_projection_frontend_events_stream_endpoint_is_projection_only() -> None:
    source = _function_source("stream_knowledge_frontend_workflow_events")

    assert "PostgresFrontendWorkflowEventRepository" in source
    for forbidden_marker in (
        "fetch_workbench_workflow_live_state",
        "workflow_live_state_changed",
        "add_listener",
        "remove_listener",
        "_drain_workflow_from_live_state_poll",
        "make_knowledge_extraction_workflow_resume",
        "RunKnowledgeExtractionWorkflowResumeCommand",
        "BackgroundTasks",
        ".add_task",
    ):
        assert forbidden_marker not in source
