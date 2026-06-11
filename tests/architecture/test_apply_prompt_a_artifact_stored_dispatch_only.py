from __future__ import annotations

from pathlib import Path


HANDLER_PATH = Path(
    "src/contexts/knowledge_workbench/extraction/application/process_managers/"
    "apply_draft_claim_observation_artifact_on_artifact_stored.py"
)


def test_apply_prompt_a_artifact_stored_handler_uses_dispatch_provenance_only() -> None:
    source = HANDLER_PATH.read_text(encoding="utf-8")

    required = (
        "ClaimExtractionDispatchArtifactProvenance",
        "from_parsed_artifact_payload_fields",
        "ApplyDraftClaimObservationArtifactAsync",
    )
    for marker in required:
        assert marker in source


def test_apply_prompt_a_artifact_stored_handler_retires_task_centric_path() -> None:
    source = HANDLER_PATH.read_text(encoding="utf-8")

    forbidden = (
        "ClaimExtractionArtifactProvenance",
        "llm_task_id",
        "llm_attempt_id",
        "ClaimExtractionPromptAArtifactFactory",
        "GroqDispatchExecutor",
        "GroqProviderAdapter",
        "LlmProviderPort",
        "ExecuteLlmTask",
        "ExecuteAndRecordLlmTask",
        "RecordWorkItemAttemptOutcome",
        "PersistArtifact",
        "capacity_runtime",
        "outbox",
        "TODO(cutover)",
        "legacy",
    )
    for marker in forbidden:
        assert marker not in source
