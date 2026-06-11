from __future__ import annotations

from pathlib import Path


COMPOSITION_PATH = Path(
    "src/interfaces/composition/persist_successful_llm_dispatch_artifacts.py",
)


def test_persist_successful_llm_dispatch_artifacts_required_markers_exist() -> None:
    source = COMPOSITION_PATH.read_text(encoding="utf-8")

    required = (
        "PersistSuccessfulLlmDispatchArtifacts",
        "PersistSuccessfulLlmDispatchArtifactsCommand",
        "PersistSuccessfulLlmDispatchArtifactsResult",
        "PersistArtifact",
        "LlmDispatchExecutionStatus.SUCCEEDED",
        "llm_dispatch_output",
    )
    for marker in required:
        assert marker in source


def test_persist_successful_llm_dispatch_artifacts_boundaries() -> None:
    source = COMPOSITION_PATH.read_text(encoding="utf-8")

    forbidden = (
        "knowledge_workbench",
        "draft_claim",
        "claim",
        "Prompt",
        "GroqDispatchExecutor",
        "GroqProviderAdapter",
        "LlmProviderPort",
        "ExecuteLlmTask",
        "ExecuteAndRecordLlmTask",
        "RecordWorkItemAttemptOutcome",
        "capacity_runtime",
        "os.environ",
        "GROQ_API_KEY",
        "httpx",
        "requests",
    )
    for marker in forbidden:
        assert marker not in source
