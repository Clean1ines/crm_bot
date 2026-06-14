from __future__ import annotations

from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_after_upload_wires_postgres_compaction_plan_repository_into_drain() -> None:
    text = _read(
        "src/interfaces/composition/knowledge_extraction_workflow_after_upload.py"
    )

    assert "PostgresDraftClaimCompactionPlanRepository" in text
    assert "DraftClaimCompactionPlanConnectionLike" in text
    assert "draft_claim_compaction_plan_repository=(" in text


def test_resume_wires_postgres_compaction_plan_repository_into_drain() -> None:
    text = _read("src/interfaces/composition/knowledge_extraction_workflow_resume.py")

    assert "PostgresDraftClaimCompactionPlanRepository" in text
    assert "DraftClaimCompactionPlanConnectionLike" in text
    assert "draft_claim_compaction_plan_repository=(" in text


def test_dispatcher_keeps_cluster_command_blocked_without_compaction_dependency() -> (
    None
):
    text = _read(
        "src/contexts/knowledge_workbench/application/sagas/"
        "dispatch_knowledge_extraction_workflow_command.py"
    )

    assert "KnowledgeExtractionCanonicalCommandType.CLUSTER_DRAFT_CLAIMS" in text
    assert "draft_claim_compaction_plan_repository is None" in text
    assert "COMMAND_HANDLER_NOT_IMPLEMENTED" in text
