from __future__ import annotations

from pathlib import Path


FACTORY_PATH = Path(
    "src/contexts/knowledge_workbench/extraction/application/policies/"
    "claim_extraction_dispatch_prompt_a_artifact_factory.py",
)


def test_claim_extraction_dispatch_prompt_a_artifact_factory_required_markers() -> None:
    source = FACTORY_PATH.read_text(encoding="utf-8")

    required = (
        "ClaimExtractionDispatchPromptAArtifactFactory",
        "ClaimExtractionDispatchPromptAArtifacts",
        "ClaimExtractionDispatchArtifactProvenance",
        "claim-extraction-dispatch",
        "DISPATCH_PROMPT_A_RAW_CLAIM_OBSERVATIONS_ARTIFACT_KIND",
        "DISPATCH_PROMPT_A_PARSED_CLAIM_OBSERVATIONS_ARTIFACT_KIND",
    )
    for marker in required:
        assert marker in source


def test_claim_extraction_dispatch_prompt_a_artifact_factory_boundaries() -> None:
    source = FACTORY_PATH.read_text(encoding="utf-8")

    forbidden = (
        "ClaimExtractionArtifactProvenance",
        "llm_task_id",
        "llm_attempt_id",
        "LlmTask",
        "LlmAttempt",
        "LlmProviderPort",
        "ExecuteLlmTask",
        "ExecuteAndRecordLlmTask",
        "GroqDispatchExecutor",
        "GroqProviderAdapter",
        "RecordWorkItemAttemptOutcome",
        "PersistArtifact",
        "outbox",
        "capacity_runtime",
    )
    for marker in forbidden:
        assert marker not in source
