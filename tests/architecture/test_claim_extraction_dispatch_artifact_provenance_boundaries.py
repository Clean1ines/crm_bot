from __future__ import annotations

from pathlib import Path


POLICY_PATH = Path(
    "src/contexts/knowledge_workbench/extraction/application/policies/"
    "claim_extraction_dispatch_artifact_provenance.py",
)


def test_claim_extraction_dispatch_artifact_provenance_required_markers() -> None:
    source = POLICY_PATH.read_text(encoding="utf-8")

    required = (
        "ClaimExtractionDispatchArtifactProvenance",
        "InvalidClaimExtractionDispatchArtifactProvenance",
        "from_llm_dispatch_output_payload",
        "work_item_attempt_id",
        "prompt_id",
        "prompt_version",
        "DISPATCH_PARSED_ARTIFACT_PAYLOAD_FIELD_NAMES",
        "DISPATCH_RAW_ARTIFACT_PAYLOAD_FIELD_NAMES",
    )
    for marker in required:
        assert marker in source


def test_claim_extraction_dispatch_artifact_provenance_boundaries() -> None:
    source = POLICY_PATH.read_text(encoding="utf-8")

    forbidden = (
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
