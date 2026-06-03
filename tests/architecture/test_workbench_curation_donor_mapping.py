from __future__ import annotations

from pathlib import Path


WORKBENCH_CURATION_FILES = (
    "src/domain/project_plane/knowledge_workbench/curation.py",
    "src/application/services/faq_workbench_surface_curation_service.py",
    "tests/domain/test_knowledge_workbench_surface_curation_policy.py",
    "tests/application/services/test_faq_workbench_surface_curation_service.py",
)

FORBIDDEN_MARKERS = (
    "KnowledgeEntryStatus",
    "KnowledgeEntryVisibility",
    "CanonicalKnowledgeEntry",
    "knowledge_compilation",
    "AnswerCandidate",
    "CandidateCluster",
    "CompilerRun",
    "CompilerRunStatus",
)


def test_workbench_curation_does_not_carry_old_canonical_entry_lifecycle() -> None:
    for path in WORKBENCH_CURATION_FILES:
        source = Path(path).read_text(encoding="utf-8")

        for marker in FORBIDDEN_MARKERS:
            assert marker not in source, f"{path} must not reference {marker}"


def test_old_publish_and_background_job_actions_are_not_draft_surface_curation() -> (
    None
):
    source = Path("src/domain/project_plane/knowledge_workbench/curation.py").read_text(
        encoding="utf-8"
    )

    assert "publish_entry" not in source
    assert "unpublish_entry" not in source
    assert "rebuild_embedding" not in source
    assert "rerun_eval" not in source
