from __future__ import annotations

from pathlib import Path


CONTRACT_PATH = Path(
    "src/contexts/llm_runtime/application/results/"
    "llm_dispatch_output_artifact_payload.py",
)


def test_llm_dispatch_output_artifact_payload_contract_required_markers() -> None:
    source = CONTRACT_PATH.read_text(encoding="utf-8")

    required = (
        "LlmDispatchOutputArtifactPayload",
        "LLM_DISPATCH_OUTPUT_ARTIFACT_KIND_VALUE",
        "llm_dispatch_output",
        "prompt_a_provenance_seed",
        "provider_messages",
        "raw_text",
        "to_mapping",
        "from_mapping",
    )
    for marker in required:
        assert marker in source


def test_llm_dispatch_output_artifact_payload_contract_boundaries() -> None:
    source = CONTRACT_PATH.read_text(encoding="utf-8")

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
        "PersistArtifact",
        "from src.contexts.artifact_runtime",
        "import ArtifactKind",
        "import ArtifactPayload",
        "artifact_runtime.domain.value_objects.artifact_kind",
        "artifact_runtime.domain.value_objects.artifact_payload",
        "outbox",
        "capacity_runtime",
        "execution_runtime",
        "os.environ",
        "GROQ_API_KEY",
        "httpx",
        "requests",
    )
    for marker in forbidden:
        assert marker not in source
