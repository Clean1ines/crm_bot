from __future__ import annotations

from pathlib import Path


COMPOSITION_PATH = Path(
    "src/interfaces/composition/"
    "execute_prepared_llm_dispatch_attempt_with_artifacts.py",
)


def test_execute_prepared_llm_dispatch_attempt_with_artifacts_markers_exist() -> None:
    source = COMPOSITION_PATH.read_text(encoding="utf-8")

    required = (
        "ExecutePreparedLlmDispatchAttemptWithArtifacts",
        "ExecutePreparedLlmDispatchAttempt",
        "PersistSuccessfulLlmDispatchArtifacts",
        "LlmDispatchExecutionStatus.SUCCEEDED",
        "artifact_result",
    )
    for marker in required:
        assert marker in source


def test_execute_prepared_llm_dispatch_attempt_with_artifacts_boundaries() -> None:
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
        "RecordWorkItemAttemptOutcome(",
        "capacity_runtime",
        "os.environ",
        "GROQ_API_KEY",
        "httpx",
        "requests",
        "outbox",
    )
    for marker in forbidden:
        assert marker not in source
