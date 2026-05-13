from __future__ import annotations

from pathlib import Path


def test_stage_k8_application_grouping_has_no_domain_word_buckets() -> None:
    source = Path("src/application/services/knowledge_ingestion_service.py").read_text(
        encoding="utf-8"
    )

    forbidden_group_labels = (
        "manager_handoff",
        "startup_requirements",
        "business_value",
        "multitenancy",
        "knowledge_base",
    )

    for label in forbidden_group_labels:
        assert label not in source
