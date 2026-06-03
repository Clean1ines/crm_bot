from __future__ import annotations

from pathlib import Path


def test_old_ingestion_service_with_hardcoded_semantic_groups_is_deleted() -> None:
    assert not Path("src/application/services/knowledge_ingestion_service.py").exists()


def test_workbench_pipeline_owns_answer_unit_policy_instead() -> None:
    policy = Path(
        "src/domain/project_plane/knowledge_workbench/answer_unit_policy.py"
    ).read_text(encoding="utf-8")
    workbench_services = (
        Path(
            "src/application/services/faq_workbench_claim_observations_service.py"
        ).read_text(encoding="utf-8")
        + "\n"
        + Path("src/application/workbench/answer_deduplication.py").read_text(
            encoding="utf-8"
        )
    )

    assert "normalize_answer_unit" in policy
    assert "deduplicate_workbench_answer_candidates" in workbench_services
    assert "knowledge_ingestion_service" not in workbench_services
